from app.constants import METRIC_LABELS
import os
import csv
import io
import json
import math
import warnings
import pandas as pd
from datetime import datetime, date, timedelta
from sqlalchemy import func, case, and_, or_
from sqlalchemy.orm import joinedload
from flask import current_app as app, flash, url_for
from flask_login import current_user
from flask_login import current_user
from werkzeug.utils import secure_filename

from app.database import db
from app.models.models import Flock, DailyLog, Standard, Hatchability, ClinicalNote, UserActivityLog, User, House, ImportedWeeklyBenchmark, PartitionWeight, NotificationRule, GlobalStandard, Hatchability, DailyLogPhoto
from app.utils import round_to_whole, safe_commit, natural_sort_key, log_user_activity, save_note_photos, send_push_alert
from metrics import enrich_flock_data

def get_flock_stock_history(flock_id):
    """
    Returns a dictionary mapping date -> live_stock (start of day).
    Useful for batch processing vaccines without N+1 queries.
    """
    flock = Flock.query.get(flock_id)
    if not flock: return {}

    logs = DailyLog.query.filter_by(flock_id=flock_id).order_by(DailyLog.date.asc()).all()

    stock_map = {}
    current_stock = flock.intake_male + flock.intake_female

    # We assume logs are contiguous or we handle gaps by carrying forward?
    # Actually, we need stock AT any date.
    # If we iterate logs, we get stock at Log Date.
    # We can build a cumulative mortality map.

    cum_loss = 0
    # Map from Date -> Cumulative Loss BEFORE that date (Start of Day)

    for log in logs:
        stock_map[log.date] = max(0, (flock.intake_male + flock.intake_female) - cum_loss)
        cum_loss += (log.mortality_male + log.mortality_female + log.culls_male + log.culls_female)

    # Also add "today/future" if needed, but mostly we query by log dates or est_dates.
    # If est_date is in future beyond logs, use last known stock.
    stock_map['latest'] = max(0, (flock.intake_male + flock.intake_female) - cum_loss)

    return stock_map

def get_flock_stock_history_bulk(flocks):
    """
    Returns a dictionary mapping flock_id -> {date -> live_stock (start of day)}.
    Optimized for bulk processing.
    """
    if not flocks: return {}

    flock_ids = [f.id for f in flocks]

    # Fetch all logs in one query
    logs = DailyLog.query.filter(DailyLog.flock_id.in_(flock_ids)).order_by(DailyLog.flock_id, DailyLog.date.asc()).all()

    # Group logs by flock
    logs_by_flock = {}
    for log in logs:
        if log.flock_id not in logs_by_flock:
            logs_by_flock[log.flock_id] = []
        logs_by_flock[log.flock_id].append(log)

    result_map = {}

    for f in flocks:
        f_id = f.id
        stock_map = {}
        cum_loss = 0

        # Get logs for this flock
        f_logs = logs_by_flock.get(f_id, [])

        # Calculate stock history
        for log in f_logs:
            stock_map[log.date] = max(0, (f.intake_male + f.intake_female) - cum_loss)
            cum_loss += (log.mortality_male + log.mortality_female + log.culls_male + log.culls_female)

        # Add "latest" entry
        stock_map['latest'] = max(0, (f.intake_male + f.intake_female) - cum_loss)
        result_map[f_id] = stock_map

    return result_map

def calculate_male_ratio(flock_id, setting_date, flock_obj=None, logs=None, last_hatch_date=None, hatchery_records=None):
    flock = flock_obj or db.session.get(Flock, flock_id)
    if not flock: return None, False

    weekday = setting_date.weekday() # Mon=0, Tue=1 ... Fri=4

    start_date = None
    end_date = setting_date - timedelta(days=1)

    large_window = False

    if weekday == 1: # Tuesday -> Fri, Sat, Sun, Mon (4 days)
        start_date = setting_date - timedelta(days=4)
    elif weekday == 4: # Friday -> Tue, Wed, Thu (3 days)
        start_date = setting_date - timedelta(days=3)
    else:
        # Non-Standard
        if last_hatch_date:
            start_date = last_hatch_date
        else:
            if hatchery_records is not None:
                # Use cached hatchery_records (assumed sorted or at least we can just find the latest one before setting_date)
                last_hatch = None
                # Sort descending to find the first one before setting_date
                sorted_records = sorted(hatchery_records, key=lambda x: x.setting_date, reverse=True)
                for rec in sorted_records:
                    if rec.setting_date < setting_date:
                        last_hatch = rec
                        break
            else:
                # Find LAST setting date for this flock BEFORE current setting_date from DB
                last_hatch = Hatchability.query.filter_by(flock_id=flock_id)\
                    .filter(Hatchability.setting_date < setting_date)\
                    .order_by(Hatchability.setting_date.desc()).first()

            if last_hatch:
                start_date = last_hatch.setting_date
            else:
                # First time catch
                start_date = setting_date - timedelta(days=7)

    days_count = (end_date - start_date).days + 1
    if days_count > 10:
        large_window = True

    # Calculate ratios daily
    if logs is None:
        logs = DailyLog.query.filter_by(flock_id=flock_id).order_by(DailyLog.date).all()

    # Init stocks (Production)
    curr_m_prod = flock.intake_male or 0
    curr_f_prod = flock.intake_female or 0
    curr_m_hosp = 0
    curr_f_hosp = 0

    prod_start_date = flock.production_start_date
    in_prod = False

    ratios = []

    for log in logs:
        # Check Phase Switch (Reset Baseline)
        if not in_prod:
             if prod_start_date and log.date >= prod_start_date:
                 in_prod = True
                 if (flock.prod_start_male or 0) > 0 or (flock.prod_start_female or 0) > 0:
                     curr_m_prod = flock.prod_start_male or 0
                     curr_f_prod = flock.prod_start_female or 0
                     curr_m_hosp = flock.prod_start_male_hosp or 0
                     curr_f_hosp = flock.prod_start_female_hosp or 0

        # Determine Ratio for this date (Start of Day)
        # Use Prod Stocks
        if start_date <= log.date <= end_date:
             if curr_f_prod > 0:
                 r = (curr_m_prod / curr_f_prod) * 100
                 ratios.append(r)

        # Update Stocks (End of Day)
        # Male
        mort_m_prod = log.mortality_male or 0
        mort_m_hosp = log.mortality_male_hosp or 0
        cull_m_prod = log.culls_male or 0
        cull_m_hosp = log.culls_male_hosp or 0
        moved_to_hosp_m = log.males_moved_to_hosp or 0
        moved_to_prod_m = log.males_moved_to_prod or 0

        curr_m_prod = curr_m_prod - mort_m_prod - cull_m_prod - moved_to_hosp_m + moved_to_prod_m
        curr_m_hosp = curr_m_hosp - mort_m_hosp - cull_m_hosp + moved_to_hosp_m - moved_to_prod_m

        # Female
        mort_f_prod = log.mortality_female or 0
        mort_f_hosp = log.mortality_female_hosp or 0
        cull_f_prod = log.culls_female or 0
        cull_f_hosp = log.culls_female_hosp or 0
        moved_to_hosp_f = log.females_moved_to_hosp or 0
        moved_to_prod_f = log.females_moved_to_prod or 0

        curr_f_prod = curr_f_prod - mort_f_prod - cull_f_prod - moved_to_hosp_f + moved_to_prod_f
        curr_f_hosp = curr_f_hosp - mort_f_hosp - cull_f_hosp + moved_to_hosp_f - moved_to_prod_f

        if curr_m_prod < 0: curr_m_prod = 0
        if curr_f_prod < 0: curr_f_prod = 0
        if curr_m_hosp < 0: curr_m_hosp = 0
        if curr_f_hosp < 0: curr_f_hosp = 0

    if not ratios:
        return None, large_window

    avg = sum(ratios) / len(ratios)
    return avg, large_window

def calculate_flock_summary(flock, daily_stats):
    """
    Calculates the 'Summary' tab data:
    1. Dashboard: Current Totals vs Depletion Targets.
    2. Weekly Table: Cumulative metrics from Start of Production.
    """

    # 1. Determine Start of Production & Females Housed
    start_date = flock.production_start_date
    start_stock = flock.prod_start_female

    if not start_date:
        # Fallback: Try to find start date from logs (Production Week 1)
        first_prod_log = next((d for d in daily_stats if d.get('production_week') and d['production_week'] >= 1), None)
        if first_prod_log:
            start_date = first_prod_log['date']
            if start_stock == 0:
                start_stock = first_prod_log['stock_female_start']
        else:
            return None, []

    # If start_date is found but start_stock is 0 (User entered 0 or missing)
    if start_stock == 0 and start_date:
        # Find stock on that date from daily_stats
        log_on_start = next((d for d in daily_stats if d['date'] == start_date), None)
        if log_on_start:
            start_stock = log_on_start['stock_female_start']
        else:
            # If no log exactly on start date, find first log after start date
            first_log_after = next((d for d in daily_stats if d['date'] > start_date), None)
            if first_log_after:
                start_stock = first_log_after['stock_female_start']

    if start_stock <= 0:
        start_stock = 1 # Avoid div by zero

    # 2. Iterate daily_stats
    # Filter for production period
    prod_stats = [d for d in daily_stats if d['date'] >= start_date]

    # Group by Production Week

    # Standards Map
    all_standards = Standard.query.all()
    std_map = {getattr(s, 'production_week'): s for s in all_standards if hasattr(s, 'production_week') and getattr(s, 'production_week')}

    cum_eggs = 0
    cum_hatch_eggs = 0
    cum_feed = 0
    cum_chicks = 0

    summary_table = []
    dashboard_metrics = {}

    # Grouping
    by_week = {}
    for d in prod_stats:
        pw = d.get('production_week')
        if not pw: continue
        if pw not in by_week: by_week[pw] = []
        by_week[pw].append(d)

    sorted_weeks = sorted(by_week.keys())

    for pw in sorted_weeks:
        days = by_week[pw]

        # Weekly Sums
        w_eggs = sum(d['eggs_collected'] for d in days)
        w_hatch_eggs = sum(d['hatch_eggs'] for d in days)
        w_feed = sum(d['feed_f_kg'] for d in days) # Use calculated Kg from enrichment
        w_chicks = sum(d['hatched_chicks'] or 0 for d in days)

        # Update Cumulative
        cum_eggs += w_eggs
        cum_hatch_eggs += w_hatch_eggs
        cum_feed += w_feed
        cum_chicks += w_chicks

        # Metrics
        hha_total = cum_eggs / start_stock
        hha_hatch = cum_hatch_eggs / start_stock
        hha_chicks = cum_chicks / start_stock

        feed_100_chicks = (cum_feed / cum_chicks * 100) if cum_chicks > 0 else 0
        feed_100_h_eggs = (cum_feed / cum_hatch_eggs * 100) if cum_hatch_eggs > 0 else 0

        # Liveability
        last_day = days[-1]
        current_live = last_day.get('stock_female_prod_end', 0)

        liveability = (current_live / start_stock * 100)

        # Standard
        std = std_map.get(pw)
        std_hha_total = (std.std_cum_eggs_hha if std and std.std_cum_eggs_hha is not None else 0.0)
        std_hha_chicks = (std.std_cum_chicks_hha if std and std.std_cum_chicks_hha is not None else 0.0)

        # Estimate Hatching Eggs HHA Target (From Standard if available, else Global %)
        if std and std.std_cum_hatching_eggs_hha:
            std_hha_hatch = std.std_cum_hatching_eggs_hha
        else:
            # Using Global Standard if available, else 96%
            gs = GlobalStandard.query.first()
            std_he_pct = gs.std_hatching_egg_pct if gs else 96.0
            std_hha_hatch = std_hha_total * (std_he_pct / 100.0)

        row = {
            'week': pw,
            'age': days[-1]['week'], # Bio Week
            'cum_eggs_hha': round(hha_total, 1),
            'std_cum_eggs_hha': std_hha_total,
            'cum_hatch_hha': round(hha_hatch, 1),
            'std_cum_hatching_eggs_hha': round(std_hha_hatch, 1),
            'cum_chicks_hha': round(hha_chicks, 1),
            'std_cum_chicks_hha': std_hha_chicks,
            'feed_100_chicks': round(feed_100_chicks, 1),
            'feed_100_h_eggs': round(feed_100_h_eggs, 1),
            'liveability': round(liveability, 2)
        }
        summary_table.append(row)

        # Feed Targets (Placeholder or Derived if Standard table doesn't have them)
        # For now, we set them to 0 if not available to avoid hardcoded mismatch
        std_feed_chicks = 0
        std_feed_h_eggs = 0

        # Update Dashboard (Last valid week overwrites previous)
        dashboard_metrics = {
            'week': pw,
            'age': days[-1]['week'],
            'hha_total': round(hha_total, 1),
            'hha_total_std': round(std_hha_total, 1),
            'hha_hatch': round(hha_hatch, 1),
            'hha_hatch_std': round(std_hha_hatch, 1),
            'hha_chicks': round(hha_chicks, 1),
            'hha_chicks_std': round(std_hha_chicks, 1),
            'liveability': round(liveability, 2),
            'feed_100_chicks': round(feed_100_chicks, 1),
            'feed_100_chicks_std': std_feed_chicks, # Dynamic or 0
            'feed_100_h_eggs': round(feed_100_h_eggs, 1),
            'feed_100_h_eggs_std': std_feed_h_eggs # Dynamic or 0
        }

    return dashboard_metrics, summary_table

def generate_spreadsheet_data(flock, logs, standards_by_week, standards_by_prod_week):
    spreadsheet_data = []
    from metrics import enrich_flock_data
    from app.models.models import FeedCode
    flock_logs = [l for l in logs]
    enriched = enrich_flock_data(flock, flock_logs)

    # Pre-fetch FeedCodes to avoid N+1 inside the loop
    feed_codes = FeedCode.query.all()
    feed_code_map = {fc.id: fc.code for fc in feed_codes}

    for item in enriched:
        log = item['log']
        week = item['week']
        prod_week = item['production_week']

        bio_std = standards_by_week.get(week)
        prod_std = standards_by_prod_week.get(prod_week)

        notes_parts = []
        if log.clinical_notes:
            notes_parts.append(log.clinical_notes)

        list_notes = [note.caption for note in log.clinical_notes_list if note.caption]
        if list_notes:
            notes_parts.extend(list_notes)

        clinical_notes_str = ', '.join(notes_parts)

        # Get partition weights
        p_map = {pw.partition_name: pw.body_weight for pw in log.partition_weights}
        p_uni_map = {pw.partition_name: pw.uniformity for pw in log.partition_weights}

        row_data = [
            log.id,
            log.date.strftime('%Y-%m-%d'),
            item['age_days'],
            clinical_notes_str,
            log.mortality_male,
            log.mortality_female,
            log.mortality_male_hosp,
            log.mortality_female_hosp,
            log.culls_male,
            log.culls_female,
            log.culls_male_hosp,
            log.culls_female_hosp,
            log.males_moved_to_hosp,
            log.females_moved_to_hosp,
            log.males_moved_to_prod,
            log.females_moved_to_prod,
            log.feed_program,
            feed_code_map.get(log.feed_code_male_id, ''),
            feed_code_map.get(log.feed_code_female_id, ''),
            log.feed_male_gp_bird,
            log.feed_female_gp_bird,
            log.feed_cleanup_start,
            log.feed_cleanup_end,
            log.water_reading_1,
            log.water_reading_2,
            log.water_reading_3,
            True if log.flushing else False,
            log.eggs_collected,
            log.egg_weight,
            log.cull_eggs_jumbo,
            log.cull_eggs_small,
            log.cull_eggs_abnormal,
            log.cull_eggs_crack,
            True if log.is_weighing_day else False,
            log.body_weight_male,
            log.body_weight_female,
            log.uniformity_male,
            log.uniformity_female,
            log.standard_bw_male,
            log.standard_bw_female
        ]

        # Add partitions
        for i in range(1, 9):
            row_data.append(p_map.get(f'M{i}', getattr(log, f'bw_male_p{i}', None) if i <= 2 else None))
            row_data.append(p_uni_map.get(f'M{i}', getattr(log, f'unif_male_p{i}', None) if i <= 2 else None))
        for i in range(1, 9):
            row_data.append(p_map.get(f'F{i}', getattr(log, f'bw_female_p{i}', None) if i <= 4 else None))
            row_data.append(p_uni_map.get(f'F{i}', getattr(log, f'unif_female_p{i}', None) if i <= 4 else None))

        row_data.extend([
            log.light_on_time,
            log.light_off_time,
            bio_std.std_mortality_female if bio_std else 0, # Benchmark Female Mort
            prod_std.std_egg_prod if prod_std else 0,       # Benchmark Egg Prod
            bio_std.std_bw_male if bio_std else 0,        # Benchmark
            bio_std.std_bw_female if bio_std else 0       # Benchmark
        ])

        spreadsheet_data.append(row_data)

    return spreadsheet_data

def process_hatchability_import(file):
    import pandas as pd
    xls = pd.ExcelFile(file)
    # Assume data is in the "Data" sheet or the first sheet if "Data" not found
    sheet_name = "Data" if "Data" in xls.sheet_names else xls.sheet_names[0]

    # Read header first to determine structure
    df = pd.read_excel(xls, sheet_name=sheet_name)

    # Required headers logic from template
    # Template: A=Setting, B=Candling, C=Hatching, D=FlockID, E=EggSet, F=Clear, G=%, H=Rotten, I=%, J=Hatchable, K=%, L=TotalHatched, M=%, N=MaleRatio

    # We will iterate row by row.
    # Check for empty df
    if df.empty:
        return 0, 0

    # Check columns
    # If headers are 'Setting Date', 'Flock ID' etc.

    col_map = {}

    def normalize(s):
        return str(s).strip().lower().replace(' ', '_')

    for i, col in enumerate(df.columns):
        norm = normalize(col)

        # Check for explicit percentage/ratio to EXCLUDE from count fields
        is_pct = '%' in norm or norm.endswith('_p') or norm.endswith('_pct') or 'ratio' in norm or 'percentage' in norm

        if 'setting' in norm and 'date' in norm: col_map['setting_date'] = i
        elif 'candling' in norm and 'date' in norm: col_map['candling_date'] = i
        elif 'hatching' in norm and 'date' in norm: col_map['hatching_date'] = i
        elif 'flock' in norm: col_map['flock_id'] = i
        elif 'egg' in norm and 'set' in norm: col_map['egg_set'] = i

        # Prefer FIRST match for counts (to handle duplicate 'Rotten Egg' headers where first is count)
        # And strictly exclude percentage-like columns
        elif 'clear' in norm and not is_pct:
            if 'clear_eggs' not in col_map: col_map['clear_eggs'] = i

        elif 'rotten' in norm and not is_pct:
            if 'rotten_eggs' not in col_map: col_map['rotten_eggs'] = i

        elif 'hatched' in norm and ('total' in norm or 'chicks' in norm): col_map['hatched_chicks'] = i
        elif 'male' in norm and 'ratio' in norm: col_map['male_ratio'] = i

    # Fallback to fixed indices if not found (Template standard)
    if 'setting_date' not in col_map: col_map['setting_date'] = 0
    if 'candling_date' not in col_map: col_map['candling_date'] = 1
    if 'hatching_date' not in col_map: col_map['hatching_date'] = 2
    if 'flock_id' not in col_map: col_map['flock_id'] = 3
    if 'egg_set' not in col_map: col_map['egg_set'] = 4
    if 'clear_eggs' not in col_map: col_map['clear_eggs'] = 5
    if 'rotten_eggs' not in col_map: col_map['rotten_eggs'] = 7 # H
    if 'hatched_chicks' not in col_map: col_map['hatched_chicks'] = 11 # L
    if 'male_ratio' not in col_map: col_map['male_ratio'] = 13 # N

    def get_val(row, key, transform=None):
        idx = col_map.get(key)
        if idx is not None and idx < len(row):
            val = row.iloc[idx]
            if pd.isna(val): return None # Explicitly None for Blanks/NaN

            # Check for Empty String or Whitespace
            if isinstance(val, str) and not val.strip():
                return None

            if transform:
                try: return transform(val)
                except: return None
            return val
        return None

    def parse_date(d):
        if hasattr(d, 'date'): return d.date()
        if isinstance(d, str):
            for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                try: return datetime.strptime(d, fmt).date()
                except: continue
        return None

    # Pre-fetch data for matching
    all_houses = House.query.all()
    house_map = {h.name: h.id for h in all_houses} # Name -> ID

    # Fetch all flocks, organize by house
    all_flocks = Flock.query.options(joinedload(Flock.house)).order_by(Flock.intake_date.desc()).all()
    flocks_by_house = {} # house_id -> list of Flock objects sorted desc
    for f in all_flocks:
        if f.house_id not in flocks_by_house:
            flocks_by_house[f.house_id] = []
        flocks_by_house[f.house_id].append(f)

    # Caches for performance optimization (N+1 query resolution)
    logs_cache = {} # flock_id -> list of DailyLog
    hatch_cache = {} # flock_id -> list of Hatchability (sorted by setting_date)

    created_count = 0
    updated_count = 0

    for index, row in df.iterrows():
        # Validations
        s_date = get_val(row, 'setting_date', parse_date)
        f_name_input = get_val(row, 'flock_id', str)

        if not s_date or not f_name_input:
            continue

        f_name = f_name_input.strip()

        # 1. Match House
        house_id = house_map.get(f_name)
        if not house_id:
            # Skip if House not found (as per requirement)
            continue

        # 2. Match Flock in House by Date
        # Find first flock where intake_date <= s_date
        target_flock = None
        target_flock_id = None
        candidates = flocks_by_house.get(house_id, [])

        for f in candidates:
            if f.intake_date <= s_date:
                target_flock = f
                target_flock_id = f.id
                break

        if not target_flock_id:
            # No valid flock found for this date
            continue

        # Populate caches for this flock if needed
        if target_flock_id not in logs_cache:
            logs_cache[target_flock_id] = DailyLog.query.filter_by(flock_id=target_flock_id).order_by(DailyLog.date).all()
        if target_flock_id not in hatch_cache:
            hatch_cache[target_flock_id] = Hatchability.query.filter_by(flock_id=target_flock_id).order_by(Hatchability.setting_date).all()

        # Extract values (None if blank)
        c_date = get_val(row, 'candling_date', parse_date)
        h_date = get_val(row, 'hatching_date', parse_date)
        e_set = get_val(row, 'egg_set', int)
        c_eggs = get_val(row, 'clear_eggs', int)
        r_eggs = get_val(row, 'rotten_eggs', int)
        h_chicks = get_val(row, 'hatched_chicks', int)

        # Determine last_hatch_date from cache for male ratio calculation
        last_hatch_date = None
        for h_rec in reversed(hatch_cache[target_flock_id]):
            if h_rec.setting_date < s_date:
                last_hatch_date = h_rec.setting_date
                break

        # Always fetch Male Ratio from Farm Database (using optimized call)
        m_ratio, _ = calculate_male_ratio(target_flock_id, s_date,
                                          flock_obj=target_flock,
                                          logs=logs_cache[target_flock_id],
                                          last_hatch_date=last_hatch_date,
                                          hatchery_records=hatch_cache[target_flock_id])

        # Check existing record in cache
        existing = next((h_rec for h_rec in hatch_cache[target_flock_id] if h_rec.setting_date == s_date), None)
        if existing:
            # Smart Patch Update
            updated_fields = []

            # Helper to update only if not None
            def update_if_present(obj, attr, val, field_name):
                if val is not None:
                    old_val = getattr(obj, attr)
                    if old_val != val:
                        setattr(obj, attr, val)
                        updated_fields.append(field_name)

            update_if_present(existing, 'candling_date', c_date, 'Candling Date')
            update_if_present(existing, 'hatching_date', h_date, 'Hatching Date')
            update_if_present(existing, 'egg_set', e_set, 'Egg Set')
            update_if_present(existing, 'clear_eggs', c_eggs, 'Clear Eggs')
            update_if_present(existing, 'rotten_eggs', r_eggs, 'Rotten Eggs')
            update_if_present(existing, 'hatched_chicks', h_chicks, 'Hatched Chicks')

            # Implicit update of Male Ratio
            if existing.male_ratio_pct != m_ratio:
                 existing.male_ratio_pct = m_ratio

            if updated_fields:
                updated_count += 1
                # Audit Log (Console for now)
                print(f"[AUDIT] Hatchery Record updated via Excel Import (Fields: {', '.join(updated_fields)}) for Flock {target_flock_id} on {s_date}")

        else:
            # Insert Record
            # Default dates if missing
            final_c_date = c_date or (s_date + timedelta(days=18))
            final_h_date = h_date or (s_date + timedelta(days=21))

            h = Hatchability(
                flock_id=target_flock_id,
                setting_date=s_date,
                candling_date=final_c_date,
                hatching_date=final_h_date,
                egg_set=e_set or 0,
                clear_eggs=c_eggs or 0,
                rotten_eggs=r_eggs or 0,
                hatched_chicks=h_chicks or 0,
                male_ratio_pct=m_ratio
            )
            db.session.add(h)
            hatch_cache[target_flock_id].append(h)
            hatch_cache[target_flock_id].sort(key=lambda x: x.setting_date)
            created_count += 1

    safe_commit()
    return created_count, updated_count

def process_import(file, commit=True, preview=False):
    xls = pd.ExcelFile(file)
    sheets = xls.sheet_names

    ignore_sheets = ['DASHBOARD', 'CHART', 'SUMMARY', 'TEMPLATE']

    all_houses_map = {h.name: h.id for h in House.query.all()}

    flock_query = db.session.query(Flock.id, Flock.house_id, Flock.intake_date).all()
    all_flocks_map = {}
    flock_counts = {}

    for f_id, f_house_id, f_intake_date in flock_query:
        if f_intake_date:
             all_flocks_map[(f_house_id, f_intake_date)] = f_id
        flock_counts[f_house_id] = flock_counts.get(f_house_id, 0) + 1

    changes = []
    all_warnings = []

    for sheet_name in sheets:
        if sheet_name.upper() in ignore_sheets:
            continue

        # Optimization: Read the full sheet once
        df_full = pd.read_excel(xls, sheet_name=sheet_name, header=None)

        # 1. Metadata (First 10 rows)
        df_meta = df_full.iloc[:10].copy() if df_full.shape[0] > 0 else pd.DataFrame()

        def get_val(r, c):
            try:
                val = df_meta.iloc[r, c]
                return val if pd.notna(val) else None
            except IndexError:
                return None

        def parse_date(date_val):
            if pd.isna(date_val):
                return None
            if hasattr(date_val, 'date'):
                return date_val.date()
            if isinstance(date_val, str):
                formats = ['%Y-%m-%d', '%d/%m/%y', '%d/%m/%Y', '%m/%d/%Y', '%m/%d/%Y']
                for fmt in formats:
                    try:
                        return datetime.strptime(date_val, fmt).date()
                    except ValueError:
                        continue
            return None

        house_name_cell = str(get_val(1, 1)).strip()
        house_name = house_name_cell if house_name_cell and house_name_cell != 'nan' else sheet_name

        def safe_int(val):
            try: return int(float(val)) if val is not None else 0
            except: return 0

        intake_female = safe_int(get_val(2, 1))
        intake_male = safe_int(get_val(3, 1))
        intake_date_val = get_val(4, 1)

        if not intake_date_val:
            print(f"Skipping sheet {sheet_name}: No Intake Date found.")
            continue

        house_id = all_houses_map.get(house_name)
        if not house_id:
            house = House(name=house_name)
            db.session.add(house)
            db.session.flush()
            house_id = house.id
            all_houses_map[house_name] = house_id
            if commit:
                safe_commit()

        intake_date = parse_date(intake_date_val)
        if not intake_date:
            print(f"Skipping sheet {sheet_name}: Invalid Date {intake_date_val}")
            continue

        date_str = intake_date.strftime('%y%m%d')

        flock_id = all_flocks_map.get((house_id, intake_date))
        if not flock_id:
            current_count = flock_counts.get(house_id, 0)
            n = current_count + 1
            flock_uid_str = f"{house_name}_{date_str}_Batch{n}"

            flock = Flock(
                house_id=house_id,
                flock_id=flock_uid_str,
                intake_date=intake_date,
                intake_male=intake_male,
                intake_female=intake_female,
                status='Active'
            )
            db.session.add(flock)
            db.session.flush()
            flock_id = flock.id
            all_flocks_map[(house_id, intake_date)] = flock_id
            flock_counts[house_id] = n
            if commit:
                safe_commit()

            initialize_sampling_schedule(flock_id, commit=commit)
            initialize_vaccine_schedule(flock_id, commit=commit)

        existing_logs_dict = {log.date: log for log in DailyLog.query.filter_by(flock_id=flock_id).all()}

        # 2. Standards (Row 507+, 70 rows)
        if df_full.shape[0] > 507:
            df_std = df_full.iloc[507:507+70].copy()
        else:
            df_std = pd.DataFrame()

        standard_bw_map = {}
        missing_std_weeks = []

        if df_std.shape[1] > 33:
            weeks = df_std.iloc[:, 0]
            males = df_std.iloc[:, 32]
            females = df_std.iloc[:, 33]

            for w, m, f in zip(weeks, males, females):
                try:
                    week_val = int(w)
                    m_val = float(m) if pd.notna(m) else 0.0
                    f_val = float(f) if pd.notna(f) else 0.0
                    standard_bw_map[week_val] = (m_val, f_val)
                except (ValueError, TypeError):
                    if pd.notna(w):
                        missing_std_weeks.append(str(w))
                    continue

        if missing_std_weeks:
            msg = f"Warning: Standard BW data invalid for weeks: {', '.join(missing_std_weeks[:10])}. Please update manually."
            if preview:
                all_warnings.append(msg)
            else:
                flash(msg, "warning")

        # 3. Data (Header at row 8, data from 9)
        if df_full.shape[0] > 8:
            header_row = df_full.iloc[8]
            df_data = df_full.iloc[9:].copy()
            df_data.columns = header_row
            # Reset index to have 0-based index for iterrows
            df_data.reset_index(drop=True, inplace=True)
        else:
            df_data = pd.DataFrame()

        # --- Column Mapping Logic ---
        headers = [str(c).upper().strip() for c in df_data.columns]

        def find_idx(candidates, default=None):
            if isinstance(candidates, str): candidates = [candidates]

            # 1. Exact Match
            for cand in candidates:
                cand = cand.upper()
                if cand in headers:
                    return headers.index(cand)

            # 2. StartsWith Match
            for cand in candidates:
                cand = cand.upper()
                for i, h in enumerate(headers):
                    if h.startswith(cand):
                        return i

            return default

        # Indices map
        idx_date = find_idx(['DATE'], 1)

        idx_cull_m = find_idx(['CULL MALE'], 2)
        idx_cull_f = find_idx(['CULL FEMALE'], 3)
        idx_dead_m = find_idx(['DEAD MALE'], 4)
        idx_dead_f = find_idx(['DEAD FEMALE'], 5)

        idx_feed_m = find_idx(['GIVEN MALE G/B', 'MALE FEED G/B'], 16)
        idx_feed_f = find_idx(['GIVEN FEMALE G/B', 'FEMALE FEED G/B'], 17)

        idx_eggs = find_idx(['EGG COLLECTED', 'EGGS COLLECTED'], 24)
        idx_jumbo = find_idx(['JUMBO'], 25)
        idx_small = find_idx(['SMALL'], 26)
        idx_abnormal = find_idx(['ABNORMAL'], 27)
        idx_crack = find_idx(['CRACK'], 28)
        idx_egg_weight = find_idx(['GRAM EGG', 'EGG WEIGHT'], 29)

        idx_bw_m = find_idx(['MALE BODY WEIGHT'], 39)
        idx_unif_m = find_idx(['MALE UNIFORMITY'], 40)
        idx_bw_f = find_idx(['FEMALE BODY WEIGHT'], 41)
        idx_unif_f = find_idx(['FEMALE UNIFORMITY'], 42)

        idx_w1 = find_idx(['8AM (m^3)', '8AM'], 43)
        idx_w2 = find_idx(['11AM (m^3)', '11AM'], 44)
        idx_w3 = find_idx(['5PM (m^3)', '5PM'], 45)

        idx_light_on = find_idx(['LIGHT ON'], 50)
        idx_light_off = find_idx(['LIGHT OFF'], 51)
        idx_feed_start = find_idx(['FEED START'], 53)
        idx_feed_end = find_idx(['FEED END'], 54)
        idx_remarks = find_idx(['REMARKS'], 56)

        partition_rows_indices = set()
        data_rows = []
        for index, row in df_data.iterrows():
            if idx_date >= len(row): continue
            date_val = row.iloc[idx_date]
            if pd.isna(date_val):
                continue
            log_date = parse_date(date_val)
            if log_date:
                data_rows.append(row)

        i = 0
        while i < len(data_rows):
            row = data_rows[i]
            # Ensure row is long enough for critical checks
            if len(row) < 2:
                i+=1
                continue

            if idx_date >= len(row):
                i+=1
                continue

            date_val = row.iloc[idx_date]
            log_date = parse_date(date_val)

            if not log_date:
                i+=1
                continue

            def get_float(r, idx):
                if idx is None or idx >= len(r): return 0.0
                val = r.iloc[idx]
                if pd.isna(val): return 0.0
                try: return float(val)
                except (ValueError, TypeError): return 0.0

            def get_int(r, idx):
                if idx is None or idx >= len(r): return 0
                val = r.iloc[idx]
                if pd.isna(val): return 0
                try: return int(float(val))
                except (ValueError, TypeError): return 0

            def get_str(r, idx):
                if idx is None or idx >= len(r): return None
                val = r.iloc[idx]
                return str(val) if pd.notna(val) else None

            def get_time(r, idx):
                if idx is None or idx >= len(r): return None
                val = r.iloc[idx]
                if pd.isna(val): return None
                if isinstance(val, str): return val
                return val.strftime('%H:%M') if hasattr(val, 'strftime') else str(val)

            # Check for Weekly Summary Rows (High Feed)
            feed_check_m = get_float(row, idx_feed_m)
            feed_check_f = get_float(row, idx_feed_f)

            if feed_check_m > 500 or feed_check_f > 500:
                # Likely a summary row with Total Feed instead of G/B
                i+=1
                continue

            log = existing_logs_dict.get(log_date)
            is_new_log = False
            if not log:
                log = DailyLog(
                    flock_id=flock_id,
                    date=log_date,                    body_weight_male=0,
                    body_weight_female=0
                )
                db.session.add(log)
                existing_logs_dict[log_date] = log
                is_new_log = True

            log.culls_male = get_int(row, idx_cull_m)
            log.culls_female = get_int(row, idx_cull_f)
            log.mortality_male = get_int(row, idx_dead_m)
            log.mortality_female = get_int(row, idx_dead_f)

            log.feed_male_gp_bird = feed_check_m
            log.feed_female_gp_bird = feed_check_f

            log.eggs_collected = get_int(row, idx_eggs)
            log.cull_eggs_jumbo = get_int(row, idx_jumbo)
            log.cull_eggs_small = get_int(row, idx_small)
            log.cull_eggs_abnormal = get_int(row, idx_abnormal)
            log.cull_eggs_crack = get_int(row, idx_crack)
            log.egg_weight = get_float(row, idx_egg_weight)

            log.water_reading_1 = get_int(row, idx_w1)
            log.water_reading_2 = get_int(row, idx_w2)
            log.water_reading_3 = get_int(row, idx_w3)

            log.light_on_time = get_time(row, idx_light_on)
            log.light_off_time = get_time(row, idx_light_off)
            log.feed_cleanup_start = get_time(row, idx_feed_start)
            log.feed_cleanup_end = get_time(row, idx_feed_end)

            val_rem = row.iloc[idx_remarks] if (idx_remarks and len(row) > idx_remarks) else None
            if pd.notna(val_rem):
                rem_str = str(val_rem).strip()
                if rem_str and rem_str.lower() not in EMPTY_NOTE_VALUES:
                    log.clinical_notes = rem_str
                else:
                    log.clinical_notes = None
            else:
                log.clinical_notes = None

            bw_m = get_float(row, idx_bw_m)
            bw_f = get_float(row, idx_bw_f)
            unif_m = get_float(row, idx_unif_m)
            unif_f = get_float(row, idx_unif_f)

            has_bw = (bw_m > 0 or bw_f > 0)

            if has_bw:
                log.is_weighing_day = True
                days_diff = (log.date - intake_date).days
                week_num = 0 if days_diff == 0 else ((days_diff - 1) // 7) + 1 if days_diff > 0 else (days_diff // 7)
                if week_num in standard_bw_map:
                    log.standard_bw_male = round_to_whole(standard_bw_map[week_num][0])
                    log.standard_bw_female = round_to_whole(standard_bw_map[week_num][1])

                log.bw_male_p1 = round_to_whole(bw_m)
                log.unif_male_p1 = unif_m
                log.bw_female_p1 = round_to_whole(bw_f)
                log.unif_female_p1 = unif_f

                if i + 1 < len(data_rows):
                    row2 = data_rows[i+1]
                    bw_m2 = get_float(row2, idx_bw_m)
                    bw_f2 = get_float(row2, idx_bw_f)
                    if bw_m2 > 0 or bw_f2 > 0:
                        log.bw_male_p2 = round_to_whole(bw_m2)
                        log.unif_male_p2 = get_float(row2, idx_unif_m)
                        log.bw_female_p2 = round_to_whole(bw_f2)
                        log.unif_female_p2 = get_float(row2, idx_unif_f)
                        partition_rows_indices.add(i+1)

                if i + 2 < len(data_rows):
                    row3 = data_rows[i+2]
                    bw_f3 = get_float(row3, idx_bw_f)
                    if bw_f3 > 0:
                        log.bw_female_p3 = round_to_whole(bw_f3)
                        log.unif_female_p3 = get_float(row3, idx_unif_f)
                        partition_rows_indices.add(i+2)

                if i + 3 < len(data_rows):
                    row4 = data_rows[i+3]
                    bw_f4 = get_float(row4, idx_bw_f)
                    if bw_f4 > 0:
                        log.bw_female_p4 = round_to_whole(bw_f4)
                        log.unif_female_p4 = get_float(row4, idx_unif_f)
                        partition_rows_indices.add(i+3)

            if i in partition_rows_indices:
                log.body_weight_male = 0
                log.body_weight_female = 0
                log.uniformity_male = 0
                log.uniformity_female = 0
                log.is_weighing_day = False
            else:
                if has_bw:
                    m_count = 0
                    m_sum = 0
                    if (log.bw_male_p1 or 0) > 0: m_sum += log.bw_male_p1; m_count += 1
                    if (log.bw_male_p2 or 0) > 0: m_sum += log.bw_male_p2; m_count += 1
                    log.body_weight_male = round_to_whole(m_sum / m_count) if m_count > 0 else 0

                    f_count = 0
                    f_sum = 0
                    if (log.bw_female_p1 or 0) > 0: f_sum += log.bw_female_p1; f_count += 1
                    if (log.bw_female_p2 or 0) > 0: f_sum += log.bw_female_p2; f_count += 1
                    if (log.bw_female_p3 or 0) > 0: f_sum += log.bw_female_p3; f_count += 1
                    if (log.bw_female_p4 or 0) > 0: f_sum += log.bw_female_p4; f_count += 1
                    log.body_weight_female = round_to_whole(f_sum / f_count) if f_count > 0 else 0

                    m_u_sum = 0
                    if (log.unif_male_p1 or 0) > 0: m_u_sum += log.unif_male_p1
                    if (log.unif_male_p2 or 0) > 0: m_u_sum += log.unif_male_p2
                    log.uniformity_male = (m_u_sum / m_count) if m_count > 0 else 0

                    f_u_sum = 0
                    if (log.unif_female_p1 or 0) > 0: f_u_sum += log.unif_female_p1
                    if (log.unif_female_p2 or 0) > 0: f_u_sum += log.unif_female_p2
                    if (log.unif_female_p3 or 0) > 0: f_u_sum += log.unif_female_p3
                    if (log.unif_female_p4 or 0) > 0: f_u_sum += log.unif_female_p4
                    log.uniformity_female = (f_u_sum / f_count) if f_count > 0 else 0

            if preview:
                # Capture change for preview
                changes.append({
                    'date': log.date.strftime('%Y-%m-%d'),
                    'house': house_name,
                    'flock': flock_uid_str if 'flock_uid_str' in locals() else f"New Flock {house_name}",
                    'type': 'New' if is_new_log else 'Update',
                    'mortality_male': log.mortality_male,
                    'mortality_female': log.mortality_female,
                    'culls_male': log.culls_male,
                    'culls_female': log.culls_female,
                    'eggs': log.eggs_collected,
                    'feed_male_gp_bird': log.feed_male_gp_bird,
                    'feed_female_gp_bird': log.feed_female_gp_bird,
                    'water_reading_1': log.water_reading_1
                })

            i += 1

        if commit:
            safe_commit()
        else:
            db.session.flush()

        all_logs = sorted(existing_logs_dict.values(), key=lambda x: x.date)
        for i, log in enumerate(all_logs):
            if i > 0:
                prev_log = all_logs[i-1]
                if prev_log.water_reading_1 and log.water_reading_1:
                    r1_today = log.water_reading_1 / 100.0
                    r1_prev = prev_log.water_reading_1 / 100.0
                    # The intake belongs to the previous day
                    prev_log.water_intake_calculated = (r1_today - r1_prev) * 1000.0
                    db.session.add(prev_log)

                    # Ensure current log resets if not evaluated by the next day yet
                    log.water_intake_calculated = 0.0
                    db.session.add(log)

        if commit:
            safe_commit()
        else:
            db.session.flush()

        flock_obj = Flock.query.get(flock_id)
        warnings = verify_import_data(flock_obj, logs=all_logs)
        if warnings:
            if preview:
                all_warnings.extend(warnings)
            else:
                flash(f"Import Verification Warnings for {house_name}: {'; '.join(warnings[:3])}...", 'warning')

    if preview:
        db.session.rollback()
        return changes, all_warnings

def recalculate_flock_inventory(flock_id):
    """
    Recalculates males_at_start, females_at_start, and recalculates feed requirements
    by iterating chronologically from the start of the flock to avoid repetitive
    summation queries.
    """
    flock = Flock.query.get(flock_id)
    if not flock:
        return

    # Fetch all logs in order
    logs = DailyLog.query.filter_by(flock_id=flock_id).order_by(DailyLog.date.asc()).all()

    curr_males = flock.intake_male or 0
    curr_females = flock.intake_female or 0
    prev_log = None

    for log in logs:
        # Update start of day columns
        log.males_at_start = curr_males
        log.females_at_start = curr_females

        # Recalculate water intake
        if prev_log and (log.date - prev_log.date).days == 1 and log.water_reading_1 is not None and prev_log.water_reading_1 is not None:
            r1_today = log.water_reading_1 / 100.0
            r1_prev = prev_log.water_reading_1 / 100.0
            # Save the calculated intake on the previous day since the 24h consumption belongs to it
            prev_log.water_intake_calculated = (r1_today - r1_prev) * 1000.0

            # Reset current day's intake until tomorrow's reading is available
            log.water_intake_calculated = 0.0
        else:
            if not log.water_intake_calculated:
                log.water_intake_calculated = 0.0

        prev_log = log

        # Feed Multiplier Logic
        multiplier = 1.0
        if log.feed_program == 'Skip-a-day':
            multiplier = 2.0
        elif log.feed_program == '2/1':
            multiplier = 1.5


        # Update stock for the next day
        # Only mortality and culls affect total house stock.
        curr_males -= ((log.mortality_male or 0) + (log.culls_male or 0))
        curr_females -= ((log.mortality_female or 0) + (log.culls_female or 0))

    safe_commit()

def check_daily_log_completion(farm_id, selected_date):
    """
    Checks the DailyLog table for the current farm_id and selected_date.
    Returns a list of dictionaries with house info and completion status.
    If farm_id is None, returns all active flocks across the entire system.
    """
    if not selected_date:
        return []

    # Get active flocks for the given farm, or all active flocks if farm_id is None
    query = Flock.query.join(House).filter(Flock.status == 'Active')
    if farm_id:
        query = query.filter(Flock.farm_id == farm_id)

    active_flocks = query.order_by(House.name).all()

    # Pre-fetch daily logs for these flocks on the selected date
    flock_ids = [f.id for f in active_flocks]
    logs_today = DailyLog.query.filter(
        DailyLog.flock_id.in_(flock_ids),
        DailyLog.date == selected_date
    ).all()
    logs_map = {l.flock_id: l for l in logs_today}

    status_list = []
    for f in active_flocks:
        log_today = logs_map.get(f.id)
        is_done = log_today is not None and log_today.is_daily_entry_submitted
        status_list.append({
            'id': f.house_id,
            'name': f.house.name,
            'is_done': is_done
        })

    return status_list

def update_log_from_request(log, req):
    old_data = {
        'mortality_male': log.mortality_male,
        'mortality_female': log.mortality_female,
        'culls_male': log.culls_male,
        'culls_female': log.culls_female,
        'feed_male_gp_bird': log.feed_male_gp_bird,
        'feed_female_gp_bird': log.feed_female_gp_bird,
        'eggs_collected': log.eggs_collected,
        'cull_eggs_jumbo': log.cull_eggs_jumbo,
        'cull_eggs_small': log.cull_eggs_small,
        'cull_eggs_crack': log.cull_eggs_crack,
        'cull_eggs_abnormal': log.cull_eggs_abnormal,
        'water_reading_1': log.water_reading_1
    }

    log.mortality_male = int(req.form.get('mortality_male') or 0)
    log.mortality_female = int(req.form.get('mortality_female') or 0)
    log.mortality_male_hosp = int(req.form.get('mortality_male_hosp') or 0)
    log.mortality_female_hosp = int(req.form.get('mortality_female_hosp') or 0)
    log.culls_male_hosp = int(req.form.get('culls_male_hosp') or 0)
    log.culls_female_hosp = int(req.form.get('culls_female_hosp') or 0)
    log.culls_male = int(req.form.get('culls_male') or 0)
    log.culls_female = int(req.form.get('culls_female') or 0)
    log.males_moved_to_prod = int(req.form.get('males_moved_to_prod') or 0)
    log.males_moved_to_hosp = int(req.form.get('males_moved_to_hosp') or 0)
    log.females_moved_to_prod = int(req.form.get('females_moved_to_prod') or 0)
    log.females_moved_to_hosp = int(req.form.get('females_moved_to_hosp') or 0)

    log.feed_program = req.form.get('feed_program')

    fc_m_id = req.form.get('feed_code_male_id')
    log.feed_code_male_id = int(fc_m_id) if fc_m_id else None

    fc_f_id = req.form.get('feed_code_female_id')
    log.feed_code_female_id = int(fc_f_id) if fc_f_id else None

    # Fallback if only single select used (legacy)
    fc_id = req.form.get('feed_code_id')
    if fc_id and not log.feed_code_male_id:
         log.feed_code_male_id = int(fc_id)
    if fc_id and not log.feed_code_female_id:
         log.feed_code_female_id = int(fc_id)

    log.feed_male_gp_bird = float(req.form.get('feed_male_gp_bird') or 0)
    log.feed_female_gp_bird = float(req.form.get('feed_female_gp_bird') or 0)

    # Fetch logs before today to sum mortality
    # We query once and sum in Python to avoid N+1 and slow sum queries
    previous_logs = DailyLog.query.filter(
        DailyLog.flock_id == log.flock_id,
        DailyLog.date < log.date
    ).order_by(DailyLog.date.asc()).all()

    cum_mort_m = 0
    cum_culls_m = 0
    cum_mort_f = 0
    cum_culls_f = 0

    for prev_log in previous_logs:
        cum_mort_m += (prev_log.mortality_male or 0)
        cum_culls_m += (prev_log.culls_male or 0)
        cum_mort_f += (prev_log.mortality_female or 0)
        cum_culls_f += (prev_log.culls_female or 0)

    # Transfers logic: If moved to hosp, they are out of prod.
    # But wait, males in hosp still eat?
    # Assuming "Feed Male" covers all males in the house (Prod + Hosp)?
    # Usually feed is tracked per house.
    # If so, we just need Total Males Alive in House.
    # Total Alive = Intake - Total Dead - Total Culled.
    # Transfers between pens (Prod <-> Hosp) don't change house population.
    # Let's assume total stock in house.

    start_m = log.flock.intake_male or 0
    start_f = log.flock.intake_female or 0

    current_stock_m = start_m - cum_mort_m - cum_culls_m
    current_stock_f = start_f - cum_mort_f - cum_culls_f

    # Data Integrity: Validation Layer
    if log.mortality_male + log.culls_male > current_stock_m:
        raise ValueError(f"Male reductions (Mortality + Culls: {log.mortality_male + log.culls_male}) exceeds Current Stock ({current_stock_m}).")
    if log.mortality_female + log.culls_female > current_stock_f:
        raise ValueError(f"Female reductions (Mortality + Culls: {log.mortality_female + log.culls_female}) exceeds Current Stock ({current_stock_f}).")

    # Automated Alerts: Mortality Spike
    alert_triggered = False
    mort_pct_m = 0.0
    mort_pct_f = 0.0
    egg_prod_pct = 0.0

    if current_stock_m > 0:
        mort_pct_m = (log.mortality_male / current_stock_m) * 100
        if mort_pct_m > 0.5:
            flash(f"ALERT: High Male Mortality Spike ({mort_pct_m:.2f}%) detected!", "danger")
            alert_triggered = True

    if current_stock_f > 0:
        mort_pct_f = (log.mortality_female / current_stock_f) * 100
        if mort_pct_f > 0.5:
            flash(f"ALERT: High Female Mortality Spike ({mort_pct_f:.2f}%) detected!", "danger")
            alert_triggered = True

    if current_stock_f > 0 and getattr(log, 'eggs_collected', 0) > 0:
        egg_prod_pct = (log.eggs_collected / current_stock_f) * 100

    if alert_triggered:
        # Simulate sending email
        app.logger.warning(f"Mortality Alert Triggered for Flock {log.flock_id}")

    # Phase 5: Dynamic Push Alerts
    active_rules = NotificationRule.query.filter_by(is_active=True).all()
    triggered_rules = []

    metric_values = {
        'mortality_female_pct': mort_pct_f,
        'mortality_male_pct': mort_pct_m,
        'egg_production_pct': egg_prod_pct
    }

    for rule in active_rules:
        val = metric_values.get(rule.metric)
        if val is not None:
            # Evaluate operator
            if rule.operator == '>':
                is_triggered = val > rule.threshold
            elif rule.operator == '<':
                is_triggered = val < rule.threshold
            elif rule.operator == '>=':
                is_triggered = val >= rule.threshold
            elif rule.operator == '<=':
                is_triggered = val <= rule.threshold
            elif rule.operator == '==':
                is_triggered = val == rule.threshold
            else:
                is_triggered = False

            if is_triggered:
                triggered_rules.append(rule)

    if triggered_rules:
        house_name = log.flock.house.name if log.flock and log.flock.house else "Unknown House"
        for rule in triggered_rules:
            title = f"Alert: {rule.name}"
            metric_label = METRIC_LABELS.get(rule.metric, rule.metric)
            body = f"{house_name}: {rule.name} Alert! {metric_label} is {metric_values.get(rule.metric):.2f}% (Threshold: {rule.operator} {rule.threshold}%)"

            # Notify all users
            all_users = User.query.all()
            for user in all_users:
                try:
                    # Provide a URL to deep link to the flock detail
                    alert_url = url_for('view_flock', id=log.flock.id) if log.flock else '/'
                    send_push_alert(user.id, title, body, url=alert_url)
                except Exception as e:
                    app.logger.error(f"Failed to send push alert to {user.username}: {str(e)}")

    # Feed Guardian Validation
    override = req.form.get('override_validation') == 'true'
    is_feeding_attempt = log.feed_male_gp_bird > 0 or log.feed_female_gp_bird > 0

    if is_feeding_attempt and not override:
        from datetime import timedelta
        if log.feed_program == 'Skip-a-day':
            yesterday_log = DailyLog.query.filter_by(flock_id=log.flock_id, date=log.date - timedelta(days=1)).first()
            if yesterday_log and (yesterday_log.feed_male_gp_bird > 0 or yesterday_log.feed_female_gp_bird > 0):
                raise ValueError("Invalid Entry: Yesterday was an ON-day. Today must be a Fasting Day (0g) for Skip-a-Day program.")
        elif log.feed_program == '2/1':
            yesterday_log = DailyLog.query.filter_by(flock_id=log.flock_id, date=log.date - timedelta(days=1)).first()
            day_minus_2_log = DailyLog.query.filter_by(flock_id=log.flock_id, date=log.date - timedelta(days=2)).first()

            y_fed = yesterday_log and (yesterday_log.feed_male_gp_bird > 0 or yesterday_log.feed_female_gp_bird > 0)
            d2_fed = day_minus_2_log and (day_minus_2_log.feed_male_gp_bird > 0 or day_minus_2_log.feed_female_gp_bird > 0)

            if y_fed and d2_fed:
                raise ValueError("Invalid Entry: The last 2 days were ON-days. Today must be a Fasting Day (0g) for 2/1 program.")

    # Feed Multiplier Logic
    multiplier = 1.0
    if log.feed_program == 'Skip-a-day':
        multiplier = 2.0
    elif log.feed_program == '2/1':
        multiplier = 1.5

    # Calculate Total Kg
    # Formula: (g/bird * multiplier * stock) / 1000
    # Calculations are now done on the fly in metrics.py

    log.eggs_collected = int(req.form.get('eggs_collected') or 0)
    log.cull_eggs_jumbo = int(req.form.get('cull_eggs_jumbo') or 0)
    log.cull_eggs_small = int(req.form.get('cull_eggs_small') or 0)
    log.cull_eggs_abnormal = int(req.form.get('cull_eggs_abnormal') or 0)
    log.cull_eggs_crack = int(req.form.get('cull_eggs_crack') or 0)
    log.egg_weight = float(req.form.get('egg_weight') or 0)

    bw_m_val = float(req.form.get('body_weight_male') or 0)
    bw_f_val = float(req.form.get('body_weight_female') or 0)
    uni_m_val = float(req.form.get('uniformity_male') or 0)
    uni_f_val = float(req.form.get('uniformity_female') or 0)

    if log.flock.phase == 'Rearing':
        PartitionWeight.query.filter_by(log_id=log.id).delete()

        f_parts = [f'F{i}' for i in range(1, 9)]
        m_parts = [f'M{i}' for i in range(1, 9)]

        sum_bw_f = 0; count_bw_f = 0
        sum_uni_f = 0; count_uni_f = 0
        sum_bw_m = 0; count_bw_m = 0
        sum_uni_m = 0; count_uni_m = 0

        for p in f_parts + m_parts:
            bw = float(req.form.get(f'bw_{p}') or 0)
            uni = float(req.form.get(f'uni_{p}') or 0)

            if bw > 0:
                bw_whole = round_to_whole(bw)
                pw = PartitionWeight(log_id=log.id, partition_name=p, body_weight=bw_whole, uniformity=uni)
                db.session.add(pw)

                if p.startswith('F'):
                    sum_bw_f += bw_whole; count_bw_f += 1
                    if uni > 0: sum_uni_f += uni; count_uni_f += 1
                else:
                    sum_bw_m += bw_whole; count_bw_m += 1
                    if uni > 0: sum_uni_m += uni; count_uni_m += 1

        if count_bw_f > 0: bw_f_val = sum_bw_f / count_bw_f
        if count_uni_f > 0: uni_f_val = sum_uni_f / count_uni_f
        if count_bw_m > 0: bw_m_val = sum_bw_m / count_bw_m
        if count_uni_m > 0: uni_m_val = sum_uni_m / count_uni_m

    log.body_weight_male = round_to_whole(bw_m_val)
    log.body_weight_female = round_to_whole(bw_f_val)
    log.uniformity_male = uni_m_val if uni_m_val > 1.0 else (uni_m_val * 100) if uni_m_val > 0 else 0
    log.uniformity_female = uni_f_val if uni_f_val > 1.0 else (uni_f_val * 100) if uni_f_val > 0 else 0

    log.is_weighing_day = 'is_weighing_day' in req.form
    log.bw_male_p1 = round_to_whole(req.form.get('bw_M1'))
    log.bw_male_p2 = round_to_whole(req.form.get('bw_M2'))
    log.unif_male_p1 = float(req.form.get('uni_M1') or 0)
    log.unif_male_p2 = float(req.form.get('uni_M2') or 0)
    log.bw_female_p1 = round_to_whole(req.form.get('bw_F1'))
    log.bw_female_p2 = round_to_whole(req.form.get('bw_F2'))
    log.bw_female_p3 = round_to_whole(req.form.get('bw_F3'))
    log.bw_female_p4 = round_to_whole(req.form.get('bw_F4'))
    log.unif_female_p1 = float(req.form.get('uni_F1') or 0)
    log.unif_female_p2 = float(req.form.get('uni_F2') or 0)
    log.unif_female_p3 = float(req.form.get('uni_F3') or 0)
    log.unif_female_p4 = float(req.form.get('uni_F4') or 0)
    log.standard_bw_male = round_to_whole(req.form.get('standard_bw_male'))
    log.standard_bw_female = round_to_whole(req.form.get('standard_bw_female'))

    log.water_reading_1 = int(req.form.get('water_reading_1') or 0)
    log.water_reading_2 = int(req.form.get('water_reading_2') or 0)
    log.water_reading_3 = int(req.form.get('water_reading_3') or 0)
    log.flushing = True if req.form.get('flushing') else False
    log.selection_done = True if req.form.get('selection_done') else False
    log.spiking = True if req.form.get('spiking') else False

    log.light_on_time = req.form.get('light_on_time')
    log.light_off_time = req.form.get('light_off_time')
    log.feed_cleanup_start = req.form.get('feed_cleanup_start')
    log.feed_cleanup_end = req.form.get('feed_cleanup_end')

    # Only remarks is processed in the main daily log now (since clinical notes/post mortem was separated)
    remarks_val = req.form.get('remarks')
    if remarks_val and remarks_val.strip() and remarks_val.strip().lower() not in EMPTY_NOTE_VALUES:
        log.remarks = remarks_val.strip()
    else:
        log.remarks = None

    if 'photo' in req.files:
        files = req.files.getlist('photo')
        for file in files:
            if file and file.filename != '':
                date_str = log.date.strftime('%y%m%d')
                raw_name = f"{log.flock.flock_id}_{date_str}_{file.filename}"
                filename = secure_filename(raw_name)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)

                new_photo = DailyLogPhoto(
                    log_id=log.id,
                    file_path=filepath,
                    original_filename=file.filename
                )
                db.session.add(new_photo)

    from datetime import timedelta
    yesterday = log.date - timedelta(days=1)
    yesterday_log = DailyLog.query.filter_by(flock_id=log.flock_id, date=yesterday).first()

    # Update previous day's water consumption since the 24h period finishes today
    if yesterday_log:
        r1_today_real = log.water_reading_1 / 100.0
        r1_yesterday_real = yesterday_log.water_reading_1 / 100.0
        yesterday_log.water_intake_calculated = (r1_today_real - r1_yesterday_real) * 1000.0

    # Today's consumption is 0 until tomorrow's reading
    log.water_intake_calculated = 0.0

    update_clinical_notes(log, req)

    new_data = {
        'mortality_male': log.mortality_male,
        'mortality_female': log.mortality_female,
        'culls_male': log.culls_male,
        'culls_female': log.culls_female,
        'feed_male_gp_bird': log.feed_male_gp_bird,
        'feed_female_gp_bird': log.feed_female_gp_bird,
        'eggs_collected': log.eggs_collected,
        'cull_eggs_jumbo': log.cull_eggs_jumbo,
        'cull_eggs_small': log.cull_eggs_small,
        'cull_eggs_crack': log.cull_eggs_crack,
        'cull_eggs_abnormal': log.cull_eggs_abnormal,
        'water_reading_1': log.water_reading_1
    }

    changes = {k: {'old': old_data[k], 'new': new_data[k]} for k in old_data if old_data[k] != new_data[k]}
    if changes:
        log_user_activity(current_user.id, 'Edit', 'DailyLog', log.id, details=changes)

def update_clinical_notes(log, req):
    # 1. Handle Deletions
    del_ids = req.form.getlist('delete_note_ids[]')
    if del_ids:
        # Check ownership/relation
        ClinicalNote.query.filter(ClinicalNote.id.in_(del_ids), ClinicalNote.log_id == log.id).delete(synchronize_session=False)

    # 2. Handle Existing Updates
    exist_ids = req.form.getlist('existing_note_id[]')

    int_exist_ids = [int(nid) for nid in exist_ids if str(nid).isdigit()]
    existing_notes = ClinicalNote.query.filter(ClinicalNote.id.in_(int_exist_ids), ClinicalNote.log_id == log.id).all()
    notes_dict = {str(note.id): note for note in existing_notes}

    for nid in exist_ids:
        note = notes_dict.get(str(nid))
        if note:
            caption = req.form.get(f'existing_note_caption_{nid}')
            if caption is not None:
                note.caption = caption

            # Photos
            if f'existing_note_photos_{nid}' in req.files:
                files = req.files.getlist(f'existing_note_photos_{nid}')
                save_note_photos(log, note, files)

    # 3. Handle New Notes
    new_indices = req.form.getlist('extra_note_index[]')
    for idx in new_indices:
        caption = req.form.get(f'extra_note_caption_{idx}')
        # Check files
        files = req.files.getlist(f'extra_note_photos_{idx}')
        has_files = any(f.filename != '' for f in files)

        if caption or has_files:
            note = ClinicalNote(log_id=log.id, caption=caption)
            db.session.add(note)
            db.session.flush() # Get ID

            if has_files:
                save_note_photos(log, note, files)

def verify_import_data(flock, logs=None):
    weekly_records = ImportedWeeklyBenchmark.query.filter_by(flock_id=flock.id).order_by(ImportedWeeklyBenchmark.week).all()
    if logs is None:
        logs = DailyLog.query.filter_by(flock_id=flock.id).all()

    warnings = []
    agg = {}
    for log in logs:
        delta = (log.date - flock.intake_date).days
        week = 0 if delta == 0 else ((delta - 1) // 7) + 1 if delta > 0 else (delta // 7)
        if week not in agg:
            agg[week] = {'mort_f': 0, 'eggs': 0}

        agg[week]['mort_f'] += log.mortality_female
        agg[week]['eggs'] += log.eggs_collected

    for wd in weekly_records:
        if wd.week in agg:
            calc = agg[wd.week]
            if abs(calc['mort_f'] - wd.mortality_female) > 1:
                warnings.append(f"Week {wd.week}: Calc Mort F ({calc['mort_f']}) != Imported ({wd.mortality_female})")

            if abs(calc['eggs'] - wd.eggs_collected) > 5:
                warnings.append(f"Week {wd.week}: Calc Eggs ({calc['eggs']}) != Imported ({wd.eggs_collected})")

    return warnings

_PROJECTED_LAY_STD_CACHE = None

def get_projected_start_of_lay(flock):
    """
    Calculates the projected date when the flock will reach 5% egg production.
    """
    global _PROJECTED_LAY_STD_CACHE
    if not flock or not flock.intake_date:
        return None, 0

    # Find standard week where egg prod >= 5% (Cached globally per process to avoid redundant DB lookups)
    if _PROJECTED_LAY_STD_CACHE is None:
        target_std = Standard.query.filter(Standard.std_egg_prod >= 5).order_by(Standard.week.asc()).first()
        _PROJECTED_LAY_STD_CACHE = target_std.week if target_std else 24

    target_week = _PROJECTED_LAY_STD_CACHE

    days_to_add = (target_week * 7)
    projected_date = flock.intake_date + timedelta(days=days_to_add)

    days_remaining = (projected_date - date.today()).days

    return projected_date, days_remaining

def get_weekly_data_aggregated(flocks):
    """
    Aggregates data for the given flocks by ISO Week.
    Returns a dictionary structure:
    {
        '2025-W40': {
            'week_str': '2025-W40',
            'start_date': date_obj,
            'end_date': date_obj,
            'flock_data': {
                flock_id: { ... metrics ... }
            }
        }
    }
    """
    if not flocks:
        return {}

    flock_ids = [f.id for f in flocks]

    # 1. Fetch all Daily Logs
    logs = DailyLog.query.filter(DailyLog.flock_id.in_(flock_ids))\
        .order_by(DailyLog.date.desc()).all()

    # 2. Fetch all Hatchability Data
    hatch_records = Hatchability.query.filter(Hatchability.flock_id.in_(flock_ids))\
        .order_by(Hatchability.setting_date.desc()).all()

    # 3. Fetch Standards
    standards = Standard.query.all()
    std_map = {getattr(s, 'week'): s for s in standards if hasattr(s, 'week')}
    prod_std_map = {getattr(s, 'production_week'): s for s in standards if hasattr(s, 'production_week') and getattr(s, 'production_week')}

    weekly_agg = {}

    # Helper to init week entry
    def init_week(key, start_d, end_d):
        if key not in weekly_agg:
            weekly_agg[key] = {
                'week_str': key,
                'start_date': start_d,
                'end_date': end_d,
                'flock_data': {}
            }
        return weekly_agg[key]

    # Process Logs
    for log in logs:
        # Determine ISO Week
        isocal = log.date.isocalendar() # (Year, Week, Weekday)
        year, week, _ = isocal
        week_key = f"{year}-W{week:02d}"

        # Start/End of that week
        # ISO week starts on Monday
        # Python's isocalendar usage
        monday = log.date - timedelta(days=log.date.weekday())
        sunday = monday + timedelta(days=6)

        entry = init_week(week_key, monday, sunday)

        f_id = log.flock_id
        if f_id not in entry['flock_data']:
            entry['flock_data'][f_id] = {
                'mort_m': 0, 'mort_f': 0,
                'cull_m': 0, 'cull_f': 0,
                'eggs': 0,
                'feed_total_kg': 0,
                'feed_g_bird_sum_f': 0, 'feed_g_bird_count': 0,
                'bw_f_sum': 0, 'bw_f_count': 0,
                'unif_f_sum': 0, 'unif_f_count': 0,
                'stock_f_start': 0, # Need to estimate
                'log_count': 0,
                'logs': [] # Keep references for sparklines if needed
            }

        fd = entry['flock_data'][f_id]
        fd['mort_m'] += (log.mortality_male or 0)
        fd['mort_f'] += (log.mortality_female or 0)
        fd['cull_m'] += (log.culls_male or 0)
        fd['cull_f'] += (log.culls_female or 0)
        fd['eggs'] += (log.eggs_collected or 0)
        # We don't have stock for this day immediately accessible here without calculating it
        # But for 'feed_total_kg' we can just set it to 0 and rely on `enrich_flock_data` for accurate metrics later
        fd['feed_total_kg'] += 0 # Removed explicit reference to log.feed_male

        if log.feed_female_gp_bird > 0:
            fd['feed_g_bird_sum_f'] += log.feed_female_gp_bird
            fd['feed_g_bird_count'] += 1

        if log.body_weight_female > 0:
            fd['bw_f_sum'] += log.body_weight_female
            fd['bw_f_count'] += 1

        if log.uniformity_female > 0:
            fd['unif_f_sum'] += log.uniformity_female
            fd['unif_f_count'] += 1

        fd['log_count'] += 1
        fd['logs'].append(log)

    # Process Hatch Data
    # Link Hatch Data to Week of SETTING or HATCHING?
    # Usually Hatchability is reported on Hatch Date week.
    for h in hatch_records:
        isocal = h.hatching_date.isocalendar()
        year, week, _ = isocal
        week_key = f"{year}-W{week:02d}"

        monday = h.hatching_date - timedelta(days=h.hatching_date.weekday())
        sunday = monday + timedelta(days=6)

        entry = init_week(week_key, monday, sunday)
        f_id = h.flock_id

        if f_id not in entry['flock_data']:
            entry['flock_data'][f_id] = {
                # Init zeros for farm metrics if no logs exist this week
                'mort_m': 0, 'mort_f': 0, 'cull_m': 0, 'cull_f': 0, 'eggs': 0,
                'feed_total_kg': 0, 'feed_g_bird_sum_f': 0, 'feed_g_bird_count': 0,
                'bw_f_sum': 0, 'bw_f_count': 0, 'unif_f_sum': 0, 'unif_f_count': 0,
                'log_count': 0, 'logs': [],
                # Hatch Metrics
                'hatched': 0, 'set': 0
            }

        fd = entry['flock_data'][f_id]
        if 'hatched' not in fd:
            fd['hatched'] = 0
            fd['set'] = 0

        fd['hatched'] += (h.hatched_chicks or 0)
        fd['set'] += (h.egg_set or 0)

    # Calculate Rates and Standard Deviations
    # Need Stock history for Mortality %
    stock_history_bulk = get_flock_stock_history_bulk(flocks)

    flock_objs = {f.id: f for f in flocks}

    # Sort weeks descending
    sorted_weeks = sorted(weekly_agg.keys(), reverse=True)

    final_data = []

    for w_key in sorted_weeks:
        w_data = weekly_agg[w_key]
        row = {
            'week': w_key,
            'start_date': w_data['start_date'],
            'end_date': w_data['end_date'],
            'flocks': []
        }

        for f_id, data in w_data['flock_data'].items():
            flock = flock_objs.get(f_id)
            if not flock: continue

            # Age Calculation (at end of week)
            age_days = (w_data['end_date'] - flock.intake_date).days
            age_week = 0 if age_days == 0 else ((age_days - 1) // 7) + 1 if age_days > 0 else (age_days // 7)
            if age_week < 0: age_week = 0

            # Standards
            std_bio = std_map.get(age_week) # Biological Standard (BW)

            # Production Standard Lookup
            std_prod = None
            if flock.start_of_lay_date:
                start_days = (flock.start_of_lay_date - flock.intake_date).days
                start_bio_week = 0 if start_days == 0 else ((start_days - 1) // 7) + 1 if start_days > 0 else (start_days // 7)
                if age_week >= start_bio_week:
                    current_prod_week = age_week - start_bio_week + 1
                    std_prod = prod_std_map.get(current_prod_week)

            # Stock Calculation
            # Use stock at start of week
            stock_hist = stock_history_bulk.get(f_id, {})
            # Find closest date <= start_date
            start_stock_f = flock.intake_female # Default

            # We can use the stock_history keys.
            # stock_history map has date -> stock at start of that day.
            # So start_stock_f should be stock at w_data['start_date']

            # Use linear search on sorted keys as optimization
            hist_dates = sorted([d for d in stock_hist.keys() if isinstance(d, date)])
            best_date = None
            for d in hist_dates:
                if d <= w_data['start_date']:
                    best_date = d
                else:
                    break

            if best_date:
                start_stock_f = stock_hist[best_date]

            # Calculations
            mort_f_pct = (data['mort_f'] / start_stock_f * 100) if start_stock_f > 0 else 0

            hen_days = start_stock_f * 7 # Approximate
            # Precise hen days = sum daily stock?
            # If we have logs, we can sum daily stock.
            # But we aggregated logs manually.
            # Let's use simple approximation for Executive view speed.

            egg_prod_pct = (data['eggs'] / hen_days * 100) if hen_days > 0 else 0

            hatch_pct = (data.get('hatched', 0) / data.get('set', 0) * 100) if data.get('set', 0) > 0 else 0

            avg_bw_f = (data['bw_f_sum'] / data['bw_f_count']) if data['bw_f_count'] > 0 else 0
            avg_unif_f = (data['unif_f_sum'] / data['unif_f_count']) if data['unif_f_count'] > 0 else 0
            avg_feed_f = (data['feed_g_bird_sum_f'] / data['feed_g_bird_count']) if data['feed_g_bird_count'] > 0 else 0

            # Generate Sparkline Data (Daily within this week)
            # data['logs'] contains daily logs.
            # We need to sort them.
            daily_logs = sorted(data['logs'], key=lambda x: x.date)
            spark_bw = [l.body_weight_female for l in daily_logs if l.body_weight_female > 0]
            spark_eggs = [((l.eggs_collected or 0)/(start_stock_f or 1)*100) for l in daily_logs] # Approx %

            # Feed Code (Take last used)
            feed_code = "N/A"
            if daily_logs:
                last_log = daily_logs[-1]
                if last_log.feed_code_female:
                    feed_code = last_log.feed_code_female.code
                elif last_log.feed_code_male:
                    feed_code = last_log.feed_code_male.code

            flock_metrics = {
                'flock_obj': flock,
                'age_week': age_week,
                'total_eggs': data['eggs'],
                'mort_f_pct': round(mort_f_pct, 2),
                'egg_prod_pct': round(egg_prod_pct, 2),
                'hatch_pct': round(hatch_pct, 2),
                'avg_bw_f': int(avg_bw_f),
                'avg_unif_f': round(avg_unif_f, 1),
                'avg_feed_f': int(avg_feed_f),
                'feed_code': feed_code,
                'std_bw_f': std_bio.std_bw_female if std_bio else None,
                'std_egg_prod': std_prod.std_egg_prod if std_prod else None,
                'spark_bw': spark_bw,
                'spark_eggs': spark_eggs
            }

            row['flocks'].append(flock_metrics)

        final_data.append(row)

    return final_data

def calculate_grading_stats(weights):
    if not weights:
        return None

    count = len(weights)
    avg_weight = sum(weights) / count
    lower_limit = avg_weight * 0.9
    upper_limit = avg_weight * 1.1

    in_range = sum(1 for w in weights if lower_limit <= w <= upper_limit)
    uniformity = (in_range / count) * 100 if count > 0 else 0.0

    lowest = min(weights)
    highest = max(weights)

    # Bins: Floor lowest to 100, ceil highest to 100
    bin_min = int(math.floor(lowest / 100.0)) * 100
    bin_max = int(math.ceil(highest / 100.0)) * 100

    # Initialize bins with zero counts to ensure they're ordered
    bins = {}
    for b in range(bin_min, bin_max + 100, 100):
        bins[str(b)] = 0

    # Populate bins
    for w in weights:
        # Find which bin it belongs to
        # Normally, a bin like 1500 means [1450, 1550) or [1500, 1600)?
        # Looking at standard distributions, usually round to nearest 100
        # If w = 1530, round(1530/100)*100 = 1500. Let's use standard rounding.
        b_key = str(int(round(w / 100.0)) * 100)
        if b_key in bins:
            bins[b_key] += 1
        else:
            # Fallback if outside somehow
            bins[b_key] = 1

    return {
        'count': count,
        'average_weight': round(avg_weight, 2),
        'uniformity': round(uniformity, 2),
        'lowest_weight': lowest,
        'highest_weight': highest,
        'grading_bins': json.dumps(bins)
    }

def get_iso_aggregated_data_sql(flock_ids, target_year):
    """
    Aggregates data by ISO week using raw SQL for performance.
    Handles stock calculation (Intake - Cumulative Loss) dynamically.
    Returns:
    {
        'weekly': [...],
        'monthly': [...],
        'yearly': [...]
    }
    """
    if not flock_ids:
        return {'weekly': [], 'monthly': [], 'yearly': []}

    ids_tuple = tuple(flock_ids)
    if len(ids_tuple) == 1:
        ids_tuple = f"({ids_tuple[0]})"
    else:
        ids_tuple = str(ids_tuple)

    # Common CTE for calculating daily metrics
    # Determine the database dialect
    dialect = db.engine.name

    if dialect == 'sqlite':
        week_fmt = "strftime('%Y-%W', l.date)"
        month_fmt = "strftime('%Y-%m', l.date)"
        year_fmt = "strftime('%Y', l.date)"
    else:  # postgresql
        week_fmt = "to_char(l.date, 'IYYY-IW')"
        month_fmt = "to_char(l.date, 'YYYY-MM')"
        year_fmt = "to_char(l.date, 'YYYY')"

    cte_sql = f"""
    WITH DailyStock AS (
        SELECT
            l.date,
            l.flock_id,
            {week_fmt} as iso_week,
            {month_fmt} as iso_month,
            {year_fmt} as iso_year,
            l.mortality_male + l.mortality_female + l.culls_male + l.culls_female as daily_loss,
            l.mortality_female as mort_f,
            l.eggs_collected,
            0 as total_feed,
            f.intake_female + f.intake_male as intake_total,
            f.intake_female,
            f.start_of_lay_date,
            SUM(l.mortality_male + l.mortality_female + l.culls_male + l.culls_female)
                OVER (PARTITION BY l.flock_id ORDER BY l.date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) as cum_loss,
            SUM(l.mortality_female + l.culls_female)
                OVER (PARTITION BY l.flock_id ORDER BY l.date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) as cum_loss_f
        FROM daily_log l
        JOIN flock f ON l.flock_id = f.id
        WHERE l.flock_id IN {ids_tuple}
    ),
    EnrichedDaily AS (
        SELECT
            *,
            (intake_female - cum_loss_f) as stock_f_end,
            -- Stock Start of Day is End of Prev Day (approx by adding back daily loss? No, simpler: Intake - (Cum - Daily))
            (intake_female - (cum_loss_f - (mort_f + 0))) as stock_f_start
        FROM DailyStock
    )
    """

    results = {}

    # Define aggregation queries with UNION ALL to reduce db calls from 6 to 2
    # Filter by Year AND Start of Lay in the Final Step to allow cum_loss to be accurate
    combined_cte_sql = f"""
        {cte_sql},
        WeeklyLogs AS (
            SELECT
                'weekly' as type,
                iso_week as period,
                SUM(eggs_collected) as total_eggs,
                SUM(mort_f) as total_mort_f,
                SUM(stock_f_start) as total_hen_days,
                COUNT(DISTINCT date) as days_in_period
            FROM EnrichedDaily
            WHERE iso_year = :year
              AND start_of_lay_date IS NOT NULL
              AND date >= start_of_lay_date
            GROUP BY iso_week
        ),
        MonthlyLogs AS (
            SELECT
                'monthly' as type,
                iso_month as period,
                SUM(eggs_collected) as total_eggs,
                SUM(mort_f) as total_mort_f,
                SUM(stock_f_start) as total_hen_days,
                COUNT(DISTINCT date) as days_in_period
            FROM EnrichedDaily
            WHERE iso_year = :year
              AND start_of_lay_date IS NOT NULL
              AND date >= start_of_lay_date
            GROUP BY iso_month
        ),
        YearlyLogs AS (
            SELECT
                'yearly' as type,
                iso_year as period,
                SUM(eggs_collected) as total_eggs,
                SUM(mort_f) as total_mort_f,
                SUM(stock_f_start) as total_hen_days,
                COUNT(DISTINCT date) as days_in_period
            FROM EnrichedDaily
            WHERE iso_year = :year
              AND start_of_lay_date IS NOT NULL
              AND date >= start_of_lay_date
            GROUP BY iso_year
        )
        SELECT * FROM WeeklyLogs
        UNION ALL
        SELECT * FROM MonthlyLogs
        UNION ALL
        SELECT * FROM YearlyLogs
    """

    # Define Hatchery Queries based on dialect
    if dialect == 'sqlite':
        hatch_week_fmt = "strftime('%Y-%W', hatching_date)"
        hatch_month_fmt = "strftime('%Y-%m', hatching_date)"
        hatch_year_fmt = "strftime('%Y', hatching_date)"
    else: # postgresql
        hatch_week_fmt = "to_char(hatching_date, 'IYYY-IW')"
        hatch_month_fmt = "to_char(hatching_date, 'YYYY-MM')"
        hatch_year_fmt = "to_char(hatching_date, 'YYYY')"

    combined_hatch_sql = f"""
        WITH WeeklyHatch AS (
            SELECT
                'weekly' as type,
                {hatch_week_fmt} as period,
                SUM(hatched_chicks) as hatched,
                SUM(egg_set) as egg_set
            FROM hatchability
            WHERE flock_id IN {ids_tuple} AND {hatch_year_fmt} = :year
            GROUP BY period
        ),
        MonthlyHatch AS (
            SELECT
                'monthly' as type,
                {hatch_month_fmt} as period,
                SUM(hatched_chicks) as hatched,
                SUM(egg_set) as egg_set
            FROM hatchability
            WHERE flock_id IN {ids_tuple} AND {hatch_year_fmt} = :year
            GROUP BY period
        ),
        YearlyHatch AS (
            SELECT
                'yearly' as type,
                {hatch_year_fmt} as period,
                SUM(hatched_chicks) as hatched,
                SUM(egg_set) as egg_set
            FROM hatchability
            WHERE flock_id IN {ids_tuple} AND {hatch_year_fmt} = :year
            GROUP BY period
        )
        SELECT * FROM WeeklyHatch
        UNION ALL
        SELECT * FROM MonthlyHatch
        UNION ALL
        SELECT * FROM YearlyHatch
    """

    # Fetch all data at once to avoid multiple db calls
    all_logs = db.session.execute(text(combined_cte_sql), {'year': str(target_year)}).fetchall()
    all_hatch = db.session.execute(text(combined_hatch_sql), {'year': str(target_year)}).fetchall()

    # Process results into typed dictionaries
    hatch_map = {'weekly': {}, 'monthly': {}, 'yearly': {}}
    for row in all_hatch:
        # Expected tuple: (type, period, hatched, egg_set)
        type_key = row[0]
        period = row[1]
        hatched = row[2]
        egg_set = row[3]
        if period:
            hatch_map[type_key][period] = (hatched, egg_set)

    logs_by_type = {'weekly': [], 'monthly': [], 'yearly': []}
    for row in all_logs:
        # Expected tuple: (type, period, total_eggs, total_mort_f, total_hen_days, days_in_period)
        type_key = row[0]
        period = row[1]
        if period:
            logs_by_type[type_key].append({
                'period': period,
                'total_eggs': row[2] or 0,
                'total_mort_f': row[3] or 0,
                'total_hen_days': row[4] or 0,
                'days_in_period': row[5] or 0
            })

    for key in ['weekly', 'monthly', 'yearly']:
        # The frontend expects periods to be descending ordered, which is not guaranteed by UNION ALL
        sorted_logs = sorted(logs_by_type[key], key=lambda x: x['period'], reverse=True)

        processed_list = []
        for log in sorted_logs:
            period = log['period']
            total_eggs = log['total_eggs']
            total_mort = log['total_mort_f']
            total_hen_days = log['total_hen_days']
            days_in_period = log['days_in_period']

            # Hatchery
            h_data = hatch_map[key].get(period)
            hatched = h_data[0] if h_data else 0
            set_cnt = h_data[1] if h_data else 0

            # Avg Prod Females = Total Hen Days / Days in Period
            # This represents the average number of birds present on any given day in the period
            avg_stock = (total_hen_days / days_in_period) if days_in_period > 0 else 0

            # Metrics
            mort_pct = (total_mort / avg_stock * 100) if avg_stock > 0 else 0

            # Egg Prod % = Total Eggs / Total Hen Days * 100
            egg_prod_pct = (total_eggs / total_hen_days * 100) if total_hen_days > 0 else 0

            hatch_pct = (hatched / set_cnt * 100) if set_cnt > 0 else 0

            processed_list.append({
                'period': period,
                'avg_prod_females': int(avg_stock), # Renamed for clarity in template usage, but legacy template uses avg_female_stock
                'avg_female_stock': int(avg_stock), # Legacy support
                'total_eggs': total_eggs,
                'total_chicks': hatched,
                'mortality_pct': round(mort_pct, 2),
                'hatchability_pct': round(hatch_pct, 2),
                'overall_egg_prod_pct': round(egg_prod_pct, 2), # Explicit Key
                'egg_production_pct': round(egg_prod_pct, 2) # Legacy Key
            })

        results[key] = processed_list

    return results

def get_iso_aggregated_data(flocks, target_year=None):
    """
    Aggregates data across all given flocks into Weekly, Monthly, and Yearly ISO buckets.
    Returns:
    {
        'weekly': [{period, avg_female_stock, total_eggs, total_chicks, mortality_pct, hatchability_pct, egg_prod_pct}, ...],
        'monthly': [...],
        'yearly': [...]
    }
    """
    if not flocks:
        return {'weekly': [], 'monthly': [], 'yearly': []}

    global_daily = {}

    # Default to current year if None, or handle differently?
    # Requirement: Filter by year.
    filter_year = target_year if target_year else date.today().year

    # Optimization: Bulk fetch Logs and Hatchability to avoid N+1 queries
    flock_ids = [f.id for f in flocks]

    # 1. Bulk Fetch Hatchability
    all_hatch_records = Hatchability.query.filter(Hatchability.flock_id.in_(flock_ids)).all()
    hatch_by_flock = {}
    for h in all_hatch_records:
        if h.flock_id not in hatch_by_flock:
            hatch_by_flock[h.flock_id] = []
        hatch_by_flock[h.flock_id].append(h)

    # 2. Bulk Fetch Logs (Optimized to use existing relationships if available)
    logs_by_flock = {}

    # Check if flocks already have logs loaded (e.g. from joinedload)
    # If the first flock has logs loaded, assume all do to avoid N+1 checks or partial loads
    has_eager_logs = len(flocks) > 0 and 'logs' in db.inspect(flocks[0]).attrs and db.inspect(flocks[0]).attrs.logs.history.has_changes() is False

    # Actually, we can just check if f.logs is populated without triggering lazy load?
    # But accessing f.logs triggers it if not loaded.
    # We can rely on the caller ensuring efficient loading.

    # Logic: If we rely on passed flocks having logs, we skip the query.
    # But get_iso_aggregated_data is a utility.
    # Let's check if we should query.

    # For now, let's optimize specifically for when we know we have logs (from executive_dashboard)
    # We can iterate and see.

    # Safe approach: Collect logs from flocks. If empty, query DB?
    # But querying DB is what we want to avoid if they ARE loaded.

    # Let's assume for this specific performance task that we want to avoid the redundant query.
    # We will build logs_by_flock from flock.logs.

    for f in flocks:
        # We access f.logs. If it was eager loaded, good. If not, it triggers a query (N+1).
        # But since we optimized executive_dashboard to use joinedload, this is fast.
        logs_by_flock[f.id] = f.logs

    for flock in flocks:
        logs = logs_by_flock.get(flock.id, [])
        hatch_records = hatch_by_flock.get(flock.id, [])

        daily_stats = enrich_flock_data(flock, logs, hatch_records)

        for d in daily_stats:
            d_date = d['date']
            # Strict Year Filter
            if d_date.year != filter_year:
                continue

            if d_date not in global_daily:
                global_daily[d_date] = {
                    'stock_f': 0, 'eggs': 0, 'mort_f': 0,
                    'chicks': 0, 'egg_set': 0,
                    'active_flocks': 0
                }

            # Check for Production Phase Logic
            is_prod = False
            if flock.production_start_date and d_date >= flock.production_start_date:
                is_prod = True
            elif flock.phase == 'Production':
                # Fallback: if no date set, assume phase is valid for all fetched logs?
                # No, historical logs might be rearing.
                # If eggs collected > 0, assume prod.
                if d['eggs_collected'] > 0: is_prod = True

            # Stock summation (Only if in production)
            if is_prod:
                global_daily[d_date]['stock_f'] += d['stock_female_start']
                global_daily[d_date]['mort_f'] += d['mortality_female']

            global_daily[d_date]['eggs'] += d['eggs_collected']

            if d.get('hatched_chicks'):
                global_daily[d_date]['chicks'] += d['hatched_chicks']
            if d.get('egg_set'):
                global_daily[d_date]['egg_set'] += d['egg_set']

            global_daily[d_date]['active_flocks'] += 1

    buckets = {'weekly': {}, 'monthly': {}, 'yearly': {}}
    sorted_dates = sorted(global_daily.keys())

    for d_date in sorted_dates:
        day_data = global_daily[d_date]

        isocal = d_date.isocalendar()
        week_key = f"{isocal[0]}-W{isocal[1]:02d}"
        month_key = d_date.strftime('%Y-%m')
        year_key = str(d_date.year)

        for p_type, p_key in [('weekly', week_key), ('monthly', month_key), ('yearly', year_key)]:
            if p_key not in buckets[p_type]:
                buckets[p_type][p_key] = {
                    'period': p_key,
                    'sum_stock_f': 0, 'days_with_stock': 0,
                    'total_eggs': 0, 'total_mort_f': 0,
                    'total_chicks': 0, 'total_set': 0,
                    'data_days': 0
                }

            b = buckets[p_type][p_key]
            b['total_eggs'] += day_data['eggs']
            b['total_mort_f'] += day_data['mort_f']
            b['total_chicks'] += day_data['chicks']
            b['total_set'] += day_data['egg_set']
            b['data_days'] += 1
            b['sum_stock_f'] += day_data['stock_f']

    results = {'weekly': [], 'monthly': [], 'yearly': []}

    for p_type in ['weekly', 'monthly', 'yearly']:
        sorted_keys = sorted(buckets[p_type].keys(), reverse=True)

        for k in sorted_keys:
            b = buckets[p_type][k]

            avg_stock = b['sum_stock_f'] / b['data_days'] if b['data_days'] > 0 else 0
            egg_prod_pct = (b['total_eggs'] / b['sum_stock_f'] * 100) if b['sum_stock_f'] > 0 else 0
            mort_pct = (b['total_mort_f'] / avg_stock * 100) if avg_stock > 0 else 0
            hatch_pct = (b['total_chicks'] / b['total_set'] * 100) if b['total_set'] > 0 else 0

            results[p_type].append({
                'period': b['period'],
                'avg_female_stock': int(avg_stock),
                'total_eggs': b['total_eggs'],
                'total_chicks': b['total_chicks'],
                'mortality_pct': round(mort_pct, 2),
                'hatchability_pct': round(hatch_pct, 2),
                'egg_production_pct': round(egg_prod_pct, 2)
            })

    return results

def get_hatchery_analytics():
    today = date.today()

    # Common filter for Active Production Flocks
    flock_filter = and_(Flock.status == 'Active', Flock.phase == 'Production')

    # Previous Hatch
    # Max date <= today with hatched_chicks > 0
    last_hatch_date_query = db.session.query(func.max(Hatchability.hatching_date)).join(Flock).filter(
        Hatchability.hatching_date <= today,
        Hatchability.hatched_chicks > 0,
        flock_filter
    ).scalar()

    last_hatch = None
    if last_hatch_date_query:
        last_records = Hatchability.query.join(Flock).filter(
            Hatchability.hatching_date == last_hatch_date_query,
            flock_filter
        ).all()

        total_h = sum(r.hatched_chicks for r in last_records)
        total_s = sum(r.egg_set for r in last_records)
        h_pct = (total_h / total_s * 100) if total_s > 0 else 0.0
        last_hatch = {
            'date': last_hatch_date_query,
            'total_hatched': total_h,
            'hatch_pct': h_pct
        }

    # Next Hatch
    # Min date >= today (or > last_hatch_date if today was processed as Previous)
    next_filter_condition = Hatchability.hatching_date >= today
    if last_hatch and last_hatch['date'] == today:
        next_filter_condition = Hatchability.hatching_date > today

    next_hatch_date_query = db.session.query(func.min(Hatchability.hatching_date)).join(Flock).filter(
        next_filter_condition,
        Hatchability.egg_set > 0,
        flock_filter
    ).scalar()

    next_hatch = None
    if next_hatch_date_query:
        next_records = Hatchability.query.join(Flock).filter(
            Hatchability.hatching_date == next_hatch_date_query,
            flock_filter
        ).all()

        # Calculate Forecast
        all_standards = Standard.query.all()
        std_map = {getattr(s, 'week'): getattr(s, 'std_hatchability', 0.0) for s in all_standards if hasattr(s, 'week')}

        total_forecast = 0
        for r in next_records:
            age_days = (next_hatch_date_query - r.flock.intake_date).days
            age_week = 0 if age_days == 0 else ((age_days - 1) // 7) + 1 if age_days > 0 else (age_days // 7)
            std_hatch = std_map.get(age_week)
            if std_hatch is None: std_hatch = 0.0
            forecast = r.egg_set * (std_hatch / 100.0)
            total_forecast += forecast

        next_hatch = {
            'date': next_hatch_date_query,
            'forecast': int(total_forecast)
        }

    return last_hatch, next_hatch


# Add constants missing
EMPTY_NOTE_VALUES = frozenset(['none', 'nan'])

METRIC_LABELS = {
    'egg_prod_pct': 'Egg Production (%)',
    'liveability_male_pct': 'Male Liveability (%)',
    'liveability_female_pct': 'Female Liveability (%)',
    'body_weight_male': 'Male Body Weight (g)',
    'body_weight_female': 'Female Body Weight (g)',
    'uniformity_male': 'Male Uniformity (%)',
    'uniformity_female': 'Female Uniformity (%)',
    'mortality_male_pct': 'Male Mortality (%)',
    'mortality_female_pct': 'Female Mortality (%)',
    'feed_male_gp_bird': 'Male Feed (g/bird)',
    'feed_female_gp_bird': 'Female Feed (g/bird)',
    'water_consumed': 'Total Water (L)'
}


def initialize_sampling_schedule(flock_id, commit=True):
    from app.services.seed_service import initialize_sampling_schedule as init_samp
    init_samp(flock_id, commit)

def initialize_vaccine_schedule(flock_id, commit=True):
    from app.services.seed_service import initialize_vaccine_schedule as init_vacc
    init_vacc(flock_id, commit)
