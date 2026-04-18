from analytics import analyze_health_events, calculate_feed_cleanup_duration
from metrics import calculate_metrics, enrich_flock_data, aggregate_weekly_metrics, aggregate_monthly_metrics, METRICS_REGISTRY
from flask import render_template, request, redirect, flash, url_for, session, jsonify
from flask_login import login_required, current_user
from app.database import db
from app.models.models import *
from sqlalchemy.orm import joinedload
from sqlalchemy import func, or_, and_
import os
import json
from datetime import datetime, date, timedelta
import calendar
from werkzeug.utils import secure_filename
import pandas as pd
import re

def register_production_routes(app):

    from app.constants import (
        REARING_PHASES, INV_TX_TYPES_USAGE_WASTE, INV_TX_TYPES_ALL,
    )
    from app.utils import safe_commit, log_user_activity, dept_required, natural_sort_key, round_to_whole
    from app.services.data_service import get_projected_start_of_lay, get_weekly_data_aggregated, get_hatchery_analytics, calculate_flock_summary, generate_spreadsheet_data, recalculate_flock_inventory, update_log_from_request, check_daily_log_completion
    from app.services.seed_service import initialize_sampling_schedule, initialize_vaccine_schedule

    @app.route('/executive/flock/<int:id>')
    @login_required
    def executive_flock_detail(id):
        # Role Check: Admin or Management
        if not current_user.role == 'Admin' and current_user.role != 'Management':
            flash("Access Denied: Executive View Only.", "danger")
            return redirect(url_for('index'))

        active_flocks = Flock.query.options(joinedload(Flock.house)).filter_by(status='Active').all()

        if active_flocks:
                active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else ''))

        flock = Flock.query.options(joinedload(Flock.house)).filter_by(id=id).first_or_404()
        logs = DailyLog.query.options(joinedload(DailyLog.partition_weights), joinedload(DailyLog.photos), joinedload(DailyLog.clinical_notes_list)).filter_by(flock_id=id).order_by(DailyLog.date.asc()).all()

        gs = GlobalStandard.query.first()
        if not gs:
            gs = GlobalStandard()
            db.session.add(gs)
            safe_commit()

        # --- Standards Setup ---
        all_standards = Standard.query.all()
        std_map = {getattr(s, 'week'): s for s in all_standards if hasattr(s, 'week')} # Bio Map
        prod_std_map = {getattr(s, 'production_week'): s for s in all_standards if hasattr(s, 'production_week') and getattr(s, 'production_week')} # Prod Map

        std_hatch_map = {getattr(s, 'week'): (getattr(s, 'std_hatchability', 0.0) or 0.0) for s in all_standards if hasattr(s, 'week')}

        # --- Fetch Hatch Data ---
        hatch_records = Hatchability.query.filter_by(flock_id=id).order_by(Hatchability.setting_date.desc()).all()

        # --- Metrics Engine ---
        daily_stats = enrich_flock_data(flock, logs, hatch_records)

        # --- Calculate Summary Tab Data ---
        summary_dashboard, summary_table = calculate_flock_summary(flock, daily_stats)

        # Inject Shifted Standard
        for d in daily_stats:
            # Biological Standards (Mortality, BW)
            std_bio = std_map.get(d['week'])
            d['std_mortality_male'] = (std_bio.std_mortality_male if std_bio and std_bio.std_mortality_male is not None else 0.0)
            d['std_mortality_female'] = (std_bio.std_mortality_female if std_bio and std_bio.std_mortality_female is not None else 0.0)

            # Production Standards (Egg Prod)
            prod_std = None
            if d.get('production_week'):
                prod_std = prod_std_map.get(d['production_week'])

            d['std_egg_prod'] = (prod_std.std_egg_prod if prod_std and prod_std.std_egg_prod is not None else 0.0)
            d['std_hatching_egg_pct'] = (prod_std.std_hatching_egg_pct if prod_std and prod_std.std_hatching_egg_pct is not None else 0.0)

        weekly_stats = aggregate_weekly_metrics(daily_stats)

        for ws in weekly_stats:
            # Biological Standards
            std_bio = std_map.get(ws['week'])
            ws['std_mortality_male'] = (std_bio.std_mortality_male if std_bio and std_bio.std_mortality_male is not None else 0.0)
            ws['std_mortality_female'] = (std_bio.std_mortality_female if std_bio and std_bio.std_mortality_female is not None else 0.0)

            # Production Standards
            prod_std = None
            if ws.get('production_week'):
                prod_std = prod_std_map.get(ws['production_week'])

            ws['std_egg_prod'] = (prod_std.std_egg_prod if prod_std and prod_std.std_egg_prod is not None else 0.0)
            ws['std_hatching_egg_pct'] = (prod_std.std_hatching_egg_pct if prod_std and prod_std.std_hatching_egg_pct is not None else 0.0)

        medications = Medication.query.filter_by(flock_id=id).all()
        vacs = Vaccine.query.filter_by(flock_id=id).filter(Vaccine.actual_date != None).all()

        # 1. Enriched Logs
        enriched_logs = []
        def scale_pct(val):
            if val is None: return None
            if 0 < val <= 1.0: return val * 100.0
            return val

        for d in daily_stats:
            log = d['log']
            lighting_hours = 0
            if log.light_on_time and log.light_off_time:
                try:
                    fmt = '%H:%M'
                    t1 = datetime.strptime(log.light_on_time, fmt)
                    t2 = datetime.strptime(log.light_off_time, fmt)
                    diff = (t2 - t1).total_seconds() / 3600
                    if diff < 0: diff += 24
                    lighting_hours = round(diff, 1)
                except: pass

            active_meds = []
            for m in medications:
                if m.start_date <= log.date:
                    if m.end_date is None or m.end_date >= log.date:
                        active_meds.append(m.drug_name)
            meds_str = ", ".join(active_meds)

            cleanup_duration_mins = None
            if log.feed_cleanup_start and log.feed_cleanup_end:
                try:
                    from analytics import calculate_feed_cleanup_duration
                    cleanup_duration_mins = calculate_feed_cleanup_duration(log.feed_cleanup_start, log.feed_cleanup_end)
                except Exception:
                    pass
            feed_cleanup_hours = round(cleanup_duration_mins / 60.0, 1) if cleanup_duration_mins else None

            enriched_logs.append({
                'log': log,
                'stock_male': d.get('stock_male_prod_end', 0) + d.get('stock_male_hosp_end', 0),
                'stock_female': d.get('stock_female_prod_end', 0) + d.get('stock_female_hosp_end', 0),
                'lighting_hours': lighting_hours,
                'medications': meds_str,
                'egg_prod_pct': d['egg_prod_pct'],
                'total_feed': d['feed_total_kg'],
                'feed_cleanup_hours': feed_cleanup_hours,
                'egg_data': {
                    'jumbo': d['cull_eggs_jumbo'],
                    'jumbo_pct': d['cull_eggs_jumbo_pct'],
                    'small': d['cull_eggs_small'],
                    'small_pct': d['cull_eggs_small_pct'],
                    'crack': d['cull_eggs_crack'],
                    'crack_pct': d['cull_eggs_crack_pct'],
                    'abnormal': d['cull_eggs_abnormal'],
                    'abnormal_pct': d['cull_eggs_abnormal_pct'],
                    'hatching': d['hatch_eggs'],
                    'hatching_pct': d['hatch_egg_pct'],
                    'total_culls': d['cull_eggs_total'],
                    'total_culls_pct': d['cull_eggs_pct']
                }
            })

        # 2. Weekly Data
        weekly_data = []
        for ws in weekly_stats:
            w_item = {
                'week': ws['week'],
                'mortality_male': ws['mortality_male'],
                'mortality_female': ws['mortality_female'],
                'culls_male': ws['culls_male'],
                'culls_female': ws['culls_female'],
                'eggs': ws['eggs_collected'],
                'hatch_eggs_sum': ws['hatch_eggs'],
                'cull_eggs_total': ws['cull_eggs_jumbo'] + ws['cull_eggs_small'] + ws['cull_eggs_crack'] + ws['cull_eggs_abnormal'],
                'mort_pct_m': ws['mortality_male_pct'],
                'mort_pct_f': ws['mortality_female_pct'],
                'cull_pct_m': ws['culls_male_pct'],
                'cull_pct_f': ws['culls_female_pct'],
                'egg_prod_pct': ws['egg_prod_pct'],
                'hatching_egg_pct': ws['hatch_egg_pct'],
                'cull_eggs_jumbo': ws['cull_eggs_jumbo'],
                'cull_eggs_jumbo_pct': ws['cull_eggs_jumbo_pct'] * 100 if ws.get('cull_eggs_jumbo_pct') else 0,
                'cull_eggs_small': ws['cull_eggs_small'],
                'cull_eggs_small_pct': ws['cull_eggs_small_pct'] * 100 if ws.get('cull_eggs_small_pct') else 0,
                'cull_eggs_crack': ws['cull_eggs_crack'],
                'cull_eggs_crack_pct': ws['cull_eggs_crack_pct'] * 100 if ws.get('cull_eggs_crack_pct') else 0,
                'cull_eggs_abnormal': ws['cull_eggs_abnormal'],
                'cull_eggs_abnormal_pct': ws['cull_eggs_abnormal_pct'] * 100 if ws.get('cull_eggs_abnormal_pct') else 0,
                'avg_bw_male': round_to_whole(ws['body_weight_male']),
                'avg_bw_female': round_to_whole(ws['body_weight_female']),
                'notes': ws['notes'],
                'photos': ws['photos']
            }
            weekly_data.append(w_item)

        # 3. Chart Data (Daily)
        chart_data = {
            'dates': [d['date'].strftime('%Y-%m-%d') for d in daily_stats],
            'ages': [d['log'].age_week_day for d in daily_stats],
            'mortality_cum_male': [round(d['mortality_cum_male_pct'], 2) for d in daily_stats],
            'mortality_cum_female': [round(d['mortality_cum_female_pct'], 2) for d in daily_stats],
            'mortality_daily_male': [round(d['mortality_male_pct'], 2) for d in daily_stats],
            'mortality_daily_female': [round(d['mortality_female_pct'], 2) for d in daily_stats],
            'std_mortality_male': [round(d['std_mortality_male'], 3) for d in daily_stats],
            'std_mortality_female': [round(d['std_mortality_female'], 3) for d in daily_stats],
            'culls_daily_male': [round(d['culls_male_pct'], 2) for d in daily_stats],
            'culls_daily_female': [round(d['culls_female_pct'], 2) for d in daily_stats],
            'egg_prod': [round(d['egg_prod_pct'], 2) for d in daily_stats],
            'std_egg_prod': [round(d['std_egg_prod'], 2) for d in daily_stats],
            'hatch_egg_pct': [round(d['hatch_egg_pct'], 2) for d in daily_stats],
            'std_hatching_egg_pct': [round(d['std_hatching_egg_pct'], 2) for d in daily_stats],
            'cull_eggs_jumbo_pct': [round(d['cull_eggs_jumbo_pct'], 2) for d in daily_stats],
            'cull_eggs_small_pct': [round(d['cull_eggs_small_pct'], 2) for d in daily_stats],
            'cull_eggs_crack_pct': [round(d['cull_eggs_crack_pct'], 2) for d in daily_stats],
            'cull_eggs_abnormal_pct': [round(d['cull_eggs_abnormal_pct'], 2) for d in daily_stats],
            'male_ratio': [round(d['male_ratio_stock'], 2) if d['male_ratio_stock'] else 0 for d in daily_stats],
            'bw_male_std': [d['log'].standard_bw_male if d['log'].standard_bw_male > 0 else None for d in daily_stats],
            'bw_female_std': [d['log'].standard_bw_female if d['log'].standard_bw_female > 0 else None for d in daily_stats],
            'unif_male': [scale_pct(d['uniformity_male']) if d['uniformity_male'] > 0 else None for d in daily_stats],
            'unif_female': [scale_pct(d['uniformity_female']) if d['uniformity_female'] > 0 else None for d in daily_stats],
            'bw_f': [d['body_weight_female'] if d['body_weight_female'] > 0 else None for d in daily_stats],
            'bw_m': [d['body_weight_male'] if d['body_weight_male'] > 0 else None for d in daily_stats],
            'water_per_bird': [round(d['water_per_bird'], 1) if d['water_per_bird'] >= 0 else None for d in daily_stats],
            'water_feed_ratio': [round(d.get('water_feed_ratio'), 2) if d.get('water_feed_ratio') is not None and d.get('water_feed_ratio') >= 0 else None for d in daily_stats],
            'feed_male_gp_bird': [round(d['feed_male_gp_bird'], 1) for d in daily_stats],
            'feed_female_gp_bird': [round(d['feed_female_gp_bird'], 1) for d in daily_stats],
            'flushing': [d['log'].flushing for d in daily_stats],
            'notes': [],
            'medication_active': [],
            'medication_names': []
        }

        for i in range(1, 9):
            chart_data[f'bw_M{i}'] = []
            chart_data[f'bw_F{i}'] = []

        for d in daily_stats:
            log = d['log']
            p_map = {pw.partition_name: pw.body_weight for pw in log.partition_weights}
            for i in range(1, 9):
                val_m = p_map.get(f'M{i}', 0)
                if val_m == 0 and i <= 2: val_m = getattr(log, f'bw_male_p{i}', 0)
                chart_data[f'bw_M{i}'].append(val_m if val_m > 0 else None)
                val_f = p_map.get(f'F{i}', 0)
                if val_f == 0 and i <= 4: val_f = getattr(log, f'bw_female_p{i}', 0)
                chart_data[f'bw_F{i}'].append(val_f if val_f > 0 else None)

            note_obj = None

            # Construct Note
            note_parts = []
            if log.flushing: note_parts.append("[FLUSHING]")
            if log.clinical_notes: note_parts.append(log.clinical_notes)

            # Meds
            active_meds = [m.drug_name for m in medications if m.start_date <= log.date and (m.end_date is None or m.end_date >= log.date)]
            chart_data['medication_active'].append(len(active_meds) > 0)
            chart_data['medication_names'].append(", ".join(active_meds) if active_meds else "")

            # User requested to remove medication from notes, so we don't append to note_parts
            # if active_meds: note_parts.append("Meds: " + ", ".join(active_meds))

            # Vacs
            done_vacs = [v.vaccine_name for v in vacs if v.actual_date == log.date]
            if done_vacs: note_parts.append("Vac: " + ", ".join(done_vacs))

            has_photos = len(log.photos) > 0
            if note_parts or has_photos:
                photo_list = []
                for p in log.photos:
                    photo_list.append({
                        'url': url_for('uploaded_file', filename=os.path.basename(p.file_path)),
                        'name': p.original_filename or 'Photo'
                    })

                note_obj = {
                    'note': " | ".join(note_parts),
                    'photos': photo_list
                }

            chart_data['notes'].append(note_obj)

        # 4. Chart Data (Weekly)
        daily_by_week = {}
        for d in daily_stats:
            if d['week'] not in daily_by_week: daily_by_week[d['week']] = []
            daily_by_week[d['week']].append(d)

        weekly_map = {ws['week']: ws for ws in weekly_stats}
        chart_data_weekly = {
            'dates': [],
            'ages': [],
            'mortality_cum_male': [], 'mortality_cum_female': [],
            'mortality_weekly_male': [], 'mortality_weekly_female': [],
            'std_mortality_male': [], 'std_mortality_female': [],
            'culls_weekly_male': [], 'culls_weekly_female': [],
            'avg_bw_male': [], 'avg_bw_female': [],
            'egg_prod': [],
            'bw_male_std': [], 'bw_female_std': [],
            'unif_male': [], 'unif_female': [],
            'notes': []
        }
        for i in range(1, 9):
            chart_data_weekly[f'bw_M{i}'] = []
            chart_data_weekly[f'bw_F{i}'] = []

        for w in sorted(weekly_map.keys()):
            ws = weekly_map[w]
            last_day = daily_by_week[w][-1]

            chart_data_weekly['dates'].append(f"Week {w}")
            chart_data_weekly['mortality_cum_male'].append(round(last_day['mortality_cum_male_pct'], 2))
            chart_data_weekly['mortality_cum_female'].append(round(last_day['mortality_cum_female_pct'], 2))
            chart_data_weekly['mortality_weekly_male'].append(round(ws['mortality_male_pct'], 2))
            chart_data_weekly['mortality_weekly_female'].append(round(ws['mortality_female_pct'], 2))
            chart_data_weekly['culls_weekly_male'].append(round(ws['culls_male_pct'], 2))
            chart_data_weekly['culls_weekly_female'].append(round(ws['culls_female_pct'], 2))
            chart_data_weekly['avg_bw_male'].append(round_to_whole(ws['body_weight_male']) if ws['body_weight_male'] > 0 else None)
            chart_data_weekly['avg_bw_female'].append(round_to_whole(ws['body_weight_female']) if ws['body_weight_female'] > 0 else None)
            chart_data_weekly['egg_prod'].append(round(ws['egg_prod_pct'], 2))
            chart_data_weekly['std_egg_prod'] = chart_data_weekly.get('std_egg_prod', [])
            chart_data_weekly['std_egg_prod'].append(round(ws['std_egg_prod'], 2))

            chart_data_weekly['hatch_egg_pct'] = chart_data_weekly.get('hatch_egg_pct', [])
            chart_data_weekly['hatch_egg_pct'].append(round(ws['hatch_egg_pct'], 2))

            chart_data_weekly['std_hatching_egg_pct'] = chart_data_weekly.get('std_hatching_egg_pct', [])
            chart_data_weekly['std_hatching_egg_pct'].append(round(ws['std_hatching_egg_pct'], 2))

            chart_data_weekly['cull_eggs_jumbo_pct'] = chart_data_weekly.get('cull_eggs_jumbo_pct', [])
            chart_data_weekly['cull_eggs_jumbo_pct'].append(round(ws['cull_eggs_jumbo_pct'], 2))

            chart_data_weekly['cull_eggs_small_pct'] = chart_data_weekly.get('cull_eggs_small_pct', [])
            chart_data_weekly['cull_eggs_small_pct'].append(round(ws['cull_eggs_small_pct'], 2))

            chart_data_weekly['cull_eggs_crack_pct'] = chart_data_weekly.get('cull_eggs_crack_pct', [])
            chart_data_weekly['cull_eggs_crack_pct'].append(round(ws['cull_eggs_crack_pct'], 2))

            chart_data_weekly['cull_eggs_abnormal_pct'] = chart_data_weekly.get('cull_eggs_abnormal_pct', [])
            chart_data_weekly['cull_eggs_abnormal_pct'].append(round(ws['cull_eggs_abnormal_pct'], 2))

            # Standard BW - Use Biological Age (w)
            std_bio = std_map.get(w)
            chart_data_weekly['bw_male_std'].append(std_bio.std_bw_male if std_bio and std_bio.std_bw_male > 0 else None)
            chart_data_weekly['bw_female_std'].append(std_bio.std_bw_female if std_bio and std_bio.std_bw_female > 0 else None)

            chart_data_weekly['unif_male'].append(scale_pct(ws['uniformity_male']) if ws['uniformity_male'] > 0 else None)
            chart_data_weekly['unif_female'].append(scale_pct(ws['uniformity_female']) if ws['uniformity_female'] > 0 else None)

            chart_data_weekly['water_per_bird'] = chart_data_weekly.get('water_per_bird', [])
            chart_data_weekly['water_per_bird'].append(round(ws['water_per_bird'], 1) if ws.get('water_per_bird', 0) >= 0 else None)
            chart_data_weekly['water_feed_ratio'] = chart_data_weekly.get('water_feed_ratio', [])
            chart_data_weekly['water_feed_ratio'].append(round(ws.get('water_feed_ratio'), 2) if ws.get('water_feed_ratio') is not None and ws.get('water_feed_ratio') >= 0 else None)

            chart_data_weekly['feed_male_gp_bird'] = chart_data_weekly.get('feed_male_gp_bird', [])
            chart_data_weekly['feed_male_gp_bird'].append(round(ws['feed_male_gp_bird'], 1))

            chart_data_weekly['feed_female_gp_bird'] = chart_data_weekly.get('feed_female_gp_bird', [])
            chart_data_weekly['feed_female_gp_bird'].append(round(ws['feed_female_gp_bird'], 1))

            for i in range(1, 9):
                chart_data_weekly[f'bw_M{i}'].append(None)
                chart_data_weekly[f'bw_F{i}'].append(None)

            # Aggregate Weekly Notes/Photos
            week_notes = []
            week_photos = []

            # From Daily Logs
            if w in daily_by_week:
                week_logs_data = daily_by_week[w]
                if week_logs_data:
                    w_start = week_logs_data[0]['date']
                    w_end = week_logs_data[-1]['date']

                    for d in week_logs_data:
                        log = d['log']
                        if log.clinical_notes:
                            week_notes.append(f"{log.date.strftime('%d/%m')}: {log.clinical_notes}")

                        for p in log.photos:
                            week_photos.append({
                                'url': url_for('uploaded_file', filename=os.path.basename(p.file_path)),
                                'name': f"{log.date.strftime('%d/%m')} {p.original_filename or 'Photo'}"
                            })

                    # Meds
                    w_meds = set()
                    for m in medications:
                        if m.start_date <= w_end and (m.end_date is None or m.end_date >= w_start):
                            w_meds.add(m.drug_name)
                    if w_meds: week_notes.append("Meds: " + ", ".join(w_meds))

                    # Vacs
                    w_vacs = set()
                    for v in vacs:
                        if v.actual_date and w_start <= v.actual_date <= w_end:
                            w_vacs.add(v.vaccine_name)
                    if w_vacs: week_notes.append("Vac: " + ", ".join(w_vacs))

            if week_notes or week_photos:
                chart_data_weekly['notes'].append({
                    'note': " | ".join(week_notes),
                    'photos': week_photos
                })
            else:
                chart_data_weekly['notes'].append(None)

        # 5. Current Stats
        if daily_stats:
            last = daily_stats[-1]
            current_stats = {
                'male_prod': last.get('stock_male_prod_end', 0),
                'female_prod': last.get('stock_female_prod_end', 0),
                'male_hosp': last.get('stock_male_hosp_end', 0),
                'female_hosp': last.get('stock_female_hosp_end', 0),
                'male_ratio': last['male_ratio_stock'] if last.get('male_ratio_stock') else 0
            }
        else:
            current_stats = {
                'male_prod': flock.intake_male,
                'female_prod': flock.intake_female,
                'male_hosp': 0,
                'female_hosp': 0,
                'male_ratio': (flock.intake_male / flock.intake_female * 100) if flock.intake_female > 0 else 0
            }

        weekly_data.reverse()

        # Pre-check available reports for this flock
        from werkzeug.utils import secure_filename
        reports_dir = os.path.join(app.root_path, 'static', 'reports')
        available_reports = set()
        if os.path.exists(reports_dir):
            prefix_to_match = f"_{secure_filename(flock.house.name)}_"
            for f in os.listdir(reports_dir):
                if prefix_to_match in f and f.endswith(".jpg"):
                    date_str = f.split("_")[0]
                    available_reports.add(date_str)

        return render_template('flock_detail_readonly.html',
                               flock=flock,
                               available_reports=available_reports,
                               logs=list(reversed(enriched_logs)),
                               weekly_data=weekly_data,
                               chart_data=chart_data,
                               chart_data_weekly=chart_data_weekly,
                               current_stats=current_stats,
                               global_std=gs,
                               active_flocks=active_flocks,
                               hatch_records=hatch_records,
                               summary_dashboard=summary_dashboard,
                               summary_table=summary_table,
                               std_hatch_map=std_hatch_map)

    @app.route('/executive/flock_select')
    @login_required
    def flock_detail_readonly_select():
        # Role Check: Admin or Management
        if not current_user.role == 'Admin' and current_user.role != 'Management':
            flash("Access Denied: Executive View Only.", "danger")
            return redirect(url_for('index'))

        active_flocks = Flock.query.options(joinedload(Flock.house)).filter_by(status='Active').all()

        if active_flocks:
                active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else ''))

        if not active_flocks:
            flash("No active flocks found.", "warning")
            return redirect(url_for('executive_dashboard'))

        return render_template('flock_detail_readonly_select.html', active_flocks=active_flocks)

    @app.route('/executive_dashboard')
    @login_required
    def executive_dashboard():
        # Role Check: Admin or Management
        if not current_user.role == 'Admin' and current_user.role != 'Management':
            flash("Access Denied: Executive View Only.", "danger")
            return redirect(url_for('index'))

        # --- Farm Data ---
        active_flocks = Flock.query.options(joinedload(Flock.logs).joinedload(DailyLog.partition_weights), joinedload(Flock.logs).joinedload(DailyLog.photos), joinedload(Flock.logs).joinedload(DailyLog.clinical_notes_list), joinedload(Flock.house)).filter_by(status='Active').all()

        if active_flocks:
                active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else ''))

        today = date.today()

        # Inventory Check
        low_stock_items = InventoryItem.query.filter(InventoryItem.current_stock < InventoryItem.min_stock_level).all()
        low_stock_count = len(low_stock_items)
        normal_stock_items = InventoryItem.query.filter(InventoryItem.current_stock >= InventoryItem.min_stock_level).all()

        # Pre-fetch Hatchability Data (Optimization: Bulk Fetch)
        flock_ids = [f.id for f in active_flocks]
        all_hatch_records = Hatchability.query.filter(Hatchability.flock_id.in_(flock_ids)).order_by(Hatchability.setting_date.desc()).all()

        flock_hatch_map = {}
        for h in all_hatch_records:
            if h.flock_id not in flock_hatch_map:
                flock_hatch_map[h.flock_id] = {
                    'latest': h,  # First record is latest due to ordering
                    'hatched_sum': 0,
                    'set_sum': 0,
                    'records': []
                }
            flock_hatch_map[h.flock_id]['hatched_sum'] += (h.hatched_chicks or 0)
            flock_hatch_map[h.flock_id]['set_sum'] += (h.egg_set or 0)
            flock_hatch_map[h.flock_id]['records'].append(h)

        for f in active_flocks:
            h_data = flock_hatch_map.get(f.id)
            hatch_recs = h_data['records'] if h_data else []

            daily_stats = enrich_flock_data(f, f.logs, hatchability_data=hatch_recs)
            f.enriched_data = daily_stats # Cache for ISO Report with hatch data

            # Hatchery Enrichment
            if h_data:
                latest_hatch = h_data['latest']
                total_h = h_data['hatched_sum']
                total_s = h_data['set_sum']
            else:
                latest_hatch = None
                total_h = 0
                total_s = 0

            f.latest_hatch = latest_hatch
            f.latest_hatch_pct = latest_hatch.hatchability_pct if latest_hatch else 0.0

            f.cum_hatch_pct = (total_h / total_s * 100) if total_s > 0 else 0.0

            f.rearing_mort_m_pct = 0
            f.rearing_mort_f_pct = 0
            f.prod_mort_m_pct = 0
            f.prod_mort_f_pct = 0
            f.male_ratio_pct = 0
            f.has_log_today = False

            # Age
            days_age = (today - f.intake_date).days
            f.age_weeks = 0 if days_age == 0 else ((days_age - 1) // 7) + 1 if days_age > 0 else 0
            f.age_days = ((days_age - 1) % 7) + 1 if days_age > 0 else 0
            f.current_week = 0 if days_age == 0 else ((days_age - 1) // 7) + 1 if days_age > 0 else 0

            # Stats
            if daily_stats:
                last = daily_stats[-1]
                if last['date'] == today:
                    f.has_log_today = True

                if getattr(f, 'calculated_phase', f.phase) in REARING_PHASES:
                    f.rearing_mort_m_pct = last['mortality_cum_male_pct']
                    f.rearing_mort_f_pct = last['mortality_cum_female_pct']
                else:
                    f.prod_mort_m_pct = last['mortality_cum_male_pct']
                    f.prod_mort_f_pct = last['mortality_cum_female_pct']

                if last['male_ratio_stock']:
                    f.male_ratio_pct = last['male_ratio_stock']

            # Daily Stats & Trends
            f.daily_stats = {
                'mort_m_pct': 0, 'mort_f_pct': 0, 'egg_pct': 0,
                'mort_m_trend': 'flat', 'mort_f_trend': 'flat', 'egg_trend': 'flat',
                'mort_m_diff': 0, 'mort_f_diff': 0, 'egg_diff': 0,
                'has_today': False,
                'show_data': False,
                'data_date': None
            }

            stats_map = { d['date']: d for d in daily_stats }
            stats_today = stats_map.get(today)

            # Determine Display Data (Today or Latest)
            display_data = None
            if stats_today:
                f.daily_stats['has_today'] = True
                display_data = stats_today
            elif daily_stats:
                display_data = daily_stats[-1]

            if display_data:
                f.daily_stats['show_data'] = True
                f.daily_stats['data_date'] = display_data['date']

                f.daily_stats['mort_m_pct'] = display_data['mortality_male_pct']
                f.daily_stats['mort_f_pct'] = display_data['mortality_female_pct']
                f.daily_stats['egg_pct'] = display_data['egg_prod_pct']

                # Trend Calculation (vs Previous Day of DATA DATE)
                stats_prev = None
                if display_data in daily_stats:
                    idx = daily_stats.index(display_data)
                    if idx > 0:
                        stats_prev = daily_stats[idx-1]
                else:
                    prev_date = display_data['date'] - timedelta(days=1)
                    stats_prev = stats_map.get(prev_date)

                if stats_prev:
                    f.daily_stats['mort_m_diff'] = display_data['mortality_male_pct'] - stats_prev['mortality_male_pct']
                    f.daily_stats['mort_f_diff'] = display_data['mortality_female_pct'] - stats_prev['mortality_female_pct']
                    f.daily_stats['egg_diff'] = display_data['egg_prod_pct'] - stats_prev['egg_prod_pct']

                    if round(f.daily_stats['mort_m_diff'], 2) > 0: f.daily_stats['mort_m_trend'] = 'up'
                    elif round(f.daily_stats['mort_m_diff'], 2) < 0: f.daily_stats['mort_m_trend'] = 'down'

                    if round(f.daily_stats['mort_f_diff'], 2) > 0: f.daily_stats['mort_f_trend'] = 'up'
                    elif round(f.daily_stats['mort_f_diff'], 2) < 0: f.daily_stats['mort_f_trend'] = 'down'

                    if round(f.daily_stats['egg_diff'], 2) > 0: f.daily_stats['egg_trend'] = 'up'
                    elif round(f.daily_stats['egg_diff'], 2) < 0: f.daily_stats['egg_trend'] = 'down'

        # Analytics: Previous & Next Hatch Dates
        last_hatch, next_hatch = get_hatchery_analytics()

        # --- New ISO Reports ---
        # Year Filter Logic
        available_years_query = db.session.query(func.extract('year', DailyLog.date)).distinct().all()
        available_years = sorted([int(y[0]) for y in available_years_query if y[0]], reverse=True)
        if not available_years:
            available_years = [today.year]

        selected_year = request.args.get('year', type=int)
        if not selected_year:
            selected_year = available_years[0] if available_years else today.year

        active_tab = request.args.get('active_tab', 'overview')

        # Phase 3 Optimization: Python Enrichment Engine to match SSOT
        all_enriched_data = []

        # Use the active_flocks we already fetched and enriched above
        for flock in active_flocks:
            if hasattr(flock, 'enriched_data') and flock.enriched_data:
                # Filter for the selected year and append
                enriched_year = [d for d in flock.enriched_data if d['date'].year == selected_year]
                all_enriched_data.extend(enriched_year)

        weekly_agg = aggregate_weekly_metrics(all_enriched_data)
        monthly_agg = aggregate_monthly_metrics(all_enriched_data)

        iso_data = {
            'weekly': [],
            'monthly': [],
            'yearly': []
        }

        # Format weekly
        for ws in reversed(weekly_agg):  # frontend expects descending
            avg_hen = ws['stock_female_start'] - ((ws['mortality_female'] + ws['culls_female']) / 2)

            iso_data['weekly'].append({
                'period': f"Week {ws['week']}",
                'avg_female_stock': int(avg_hen),
                'total_eggs': ws['eggs_collected'],
                'total_chicks': ws['hatched_chicks'],
                'mortality_pct': ws['mortality_female_pct'],
                'hatchability_pct': ws['hatchability_pct'],
                'egg_production_pct': ws['egg_prod_pct']
            })

        # Format monthly
        for ms in reversed(monthly_agg):
            avg_hen = ms['stock_female_start'] - ((ms['mortality_female'] + ms['culls_female']) / 2)

            iso_data['monthly'].append({
                'period': ms['month'],
                'avg_female_stock': int(avg_hen),
                'total_eggs': ms['eggs_collected'],
                'total_chicks': ms['hatched_chicks'],
                'mortality_pct': ms['mortality_female_pct'],
                'hatchability_pct': ms['hatchability_pct'],
                'egg_production_pct': ms['egg_prod_pct']
            })

        # Build yearly aggregation manually since metrics.py doesn't have aggregate_yearly_metrics
        yearly_stats = {}
        for d in all_enriched_data:
            y_key = str(d['date'].year)
            if y_key not in yearly_stats:
                yearly_stats[y_key] = {
                    'period': y_key,
                    'count': 0,
                    'stock_female_start': d['stock_female_start'],
                    'mortality_female': 0,
                    'culls_female': 0,
                    'eggs_collected': 0,
                    'hatched_chicks': 0,
                    'egg_set': 0
                }

            ys = yearly_stats[y_key]
            ys['count'] += 1
            ys['mortality_female'] += d['mortality_female']
            ys['culls_female'] += d['culls_female']
            ys['eggs_collected'] += d['eggs_collected']
            if d.get('hatched_chicks'): ys['hatched_chicks'] += d['hatched_chicks']
            if d.get('egg_set'): ys['egg_set'] += d['egg_set']

        for y_key in sorted(yearly_stats.keys(), reverse=True):
            ys = yearly_stats[y_key]
            avg_hen = ys['stock_female_start'] - ((ys['mortality_female'] + ys['culls_female']) / 2)
            mortality_pct = (ys['mortality_female'] / ys['stock_female_start'] * 100) if ys['stock_female_start'] > 0 else 0
            egg_prod_pct = (ys['eggs_collected'] / (avg_hen * ys['count'])) * 100 if (avg_hen * ys['count']) > 0 else 0
            hatchability_pct = (ys['hatched_chicks'] / ys['egg_set'] * 100) if ys['egg_set'] > 0 else 0

            iso_data['yearly'].append({
                'period': y_key,
                'avg_female_stock': int(avg_hen),
                'total_eggs': ys['eggs_collected'],
                'total_chicks': ys['hatched_chicks'],
                'mortality_pct': mortality_pct,
                'hatchability_pct': hatchability_pct,
                'egg_production_pct': egg_prod_pct
            })

        # Monthly Inventory Usage Calculation
        current_month_start = today.replace(day=1)
        if current_month_start.month == 1:
            last_month_start = current_month_start.replace(year=current_month_start.year - 1, month=12)
        else:
            last_month_start = current_month_start.replace(month=current_month_start.month - 1)

        inventory_items = InventoryItem.query.all()
        inventory_usage = []

        # We will get logs for current and last month
        logs_this_month = InventoryTransaction.query.filter(
            InventoryTransaction.transaction_date >= current_month_start,
            InventoryTransaction.transaction_type.in_(['Usage', 'Waste'])
        ).all()

        logs_last_month = InventoryTransaction.query.filter(
            InventoryTransaction.transaction_date >= last_month_start,
            InventoryTransaction.transaction_date < current_month_start,
            InventoryTransaction.transaction_type.in_(['Usage', 'Waste'])
        ).all()

        for item in inventory_items:
            used_this = sum(log.quantity for log in logs_this_month if log.inventory_item_id == item.id)
            used_last = sum(log.quantity for log in logs_last_month if log.inventory_item_id == item.id)

            inventory_usage.append({
                'name': item.name,
                'type': item.type,
                'current_stock': item.current_stock,
                'unit': item.unit,
                'used_this_month': round(used_this, 2),
                'used_last_month': round(used_last, 2)
            })

        return render_template('executive_dashboard.html',
                               active_flocks=active_flocks,
                               last_hatch=last_hatch,
                               next_hatch=next_hatch,
                               current_month=today.strftime('%B %Y'),
                               today=today,
                               inventory_usage=inventory_usage,
                               iso_data=iso_data,
                               available_years=available_years,
                               selected_year=selected_year,
                               active_tab=active_tab)

    @app.route('/additional_report')
    @login_required
    def additional_report():
        # Role Check: Admin or Management
        if not current_user.role == 'Admin' and current_user.role != 'Management':
            flash("Access Denied: Executive View Only.", "danger")
            return redirect(url_for('index'))

        # Active Flocks
        active_flocks = Flock.query.filter_by(status='Active').options(joinedload(Flock.house)).all()

        if active_flocks:
                active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else ''))

        prod_flocks = [f for f in active_flocks if f.phase == 'Production']
        rearing_flocks = [f for f in active_flocks if f.phase == 'Rearing']

        # Get Aggregated Data
        # We fetch ALL data in one go or per group? One go is fine, then filter in template or here.
        # Actually, the table structure differs.

        prod_data_weekly = get_weekly_data_aggregated(prod_flocks)
        rearing_data_weekly = get_weekly_data_aggregated(rearing_flocks)

        # Countdown Logic for Rearing Flocks
        countdowns = []
        for f in rearing_flocks:
            p_date, d_rem = get_projected_start_of_lay(f)
            countdowns.append({
                'flock': f,
                'projected_date': p_date,
                'days_remaining': d_rem
            })

        # Leaderboard (Active Flocks)
        # Top House (Best Egg Prod % - Current Week?)
        # Let's use the most recent week in prod_data_weekly
        top_house = None
        best_prod = -1

        top_hatch_batch = None
        best_hatch = -1

        # Iterate latest week of production data
        if prod_data_weekly:
            latest_week = prod_data_weekly[0] # Sorted descending
            for f_metric in latest_week['flocks']:
                # Egg Prod
                if f_metric['egg_prod_pct'] > best_prod:
                    best_prod = f_metric['egg_prod_pct']
                    top_house = f_metric['flock_obj'].house.name

                # Hatch
                if f_metric['hatch_pct'] > best_hatch:
                    best_hatch = f_metric['hatch_pct']
                    top_hatch_batch = f_metric['flock_obj'].flock_id

        leaderboard = {
            'top_house': top_house,
            'best_prod': best_prod,
            'top_hatch_batch': top_hatch_batch,
            'best_hatch': best_hatch
        }

        # Inventory Usage (Monthly) - Same as before
        usage_txs = InventoryTransaction.query.options(joinedload(InventoryTransaction.item)).filter(
            InventoryTransaction.transaction_type == 'Usage'
        ).order_by(InventoryTransaction.transaction_date.desc()).all()

        inventory_usage = {}
        for tx in usage_txs:
            month_str = tx.transaction_date.strftime('%Y-%m')
            key = (month_str, tx.item.name, tx.item.unit)
            if key not in inventory_usage: inventory_usage[key] = 0.0
            inventory_usage[key] += tx.quantity

        usage_list = []
        for (month, name, unit), qty in inventory_usage.items():
            usage_list.append({'month': month, 'name': name, 'unit': unit, 'qty': qty})

        usage_list.sort(key=lambda x: x['month'], reverse=True)

        # Date Header
        today = date.today()
        current_month_name = today.strftime('%B %Y')
        isocal = today.isocalendar()
        current_iso_week = f"{isocal[0]}-W{isocal[1]:02d}"

        return render_template('additional_report.html',
                               prod_data=prod_data_weekly,
                               rearing_data=rearing_data_weekly,
                               countdowns=countdowns,
                               leaderboard=leaderboard,
                               inventory_usage=usage_list,
                               current_month=current_month_name,
                               current_iso_week=current_iso_week)

    @app.route('/inventory/transaction/edit/<int:id>', methods=['POST'])
    @login_required
    @dept_required('Farm')
    def edit_inventory_transaction(id):
        if not current_user.role == 'Admin': return redirect(url_for('index'))

        t = InventoryTransaction.query.get_or_404(id)
        item = InventoryItem.query.get(t.inventory_item_id)

        old_data = {
            'quantity': t.quantity,
            'transaction_type': t.transaction_type,
            'transaction_date': t.transaction_date.strftime('%Y-%m-%d') if t.transaction_date else None,
            'notes': t.notes
        }

        new_qty = float(request.form.get('quantity') or 0)
        new_date_str = request.form.get('transaction_date')
        new_notes = request.form.get('notes')
        new_type = request.form.get('transaction_type')

        if new_qty <= 0:
            flash("Quantity must be positive.", "danger")
            return redirect(url_for('inventory'))

        if new_type and new_type not in INV_TX_TYPES_ALL:
            flash("Invalid transaction type.", "danger")
            return redirect(url_for('inventory'))

        # Revert Old Effect
        if item:
            if t.transaction_type in INV_TX_TYPES_USAGE_WASTE:
                item.current_stock += t.quantity
            else:
                item.current_stock -= t.quantity

        # Update Transaction
        t.quantity = new_qty
        t.notes = new_notes
        if new_type:
            t.transaction_type = new_type

        if new_date_str:
            try:
                t.transaction_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
            except: pass

        new_data = {
            'quantity': t.quantity,
            'transaction_type': t.transaction_type,
            'transaction_date': t.transaction_date.strftime('%Y-%m-%d') if t.transaction_date else None,
            'notes': t.notes
        }

        changes = {k: {'old': old_data[k], 'new': new_data[k]} for k in old_data if old_data[k] != new_data[k]}
        if changes:
            log_user_activity(current_user.id, 'Edit', 'InventoryTransaction', t.id, details=changes)

        # Apply New Effect
        if item:
            if t.transaction_type in INV_TX_TYPES_USAGE_WASTE:
                item.current_stock -= new_qty
            else:
                item.current_stock += new_qty

        safe_commit()
        flash("Transaction updated.", "success")
        return redirect(url_for('inventory'))

    @app.route('/inventory/transaction/delete/<int:id>', methods=['POST'])
    @login_required
    @dept_required('Farm')
    def delete_inventory_transaction(id):
        if not current_user.role == 'Admin': return redirect(url_for('index'))

        t = InventoryTransaction.query.get_or_404(id)
        item = InventoryItem.query.get(t.inventory_item_id)
        t_type = t.transaction_type
        t_qty = t.quantity
        item_name = item.name if item else "Unknown"

        log_user_activity(current_user.id, 'Delete', 'InventoryTransaction', id, details={'item_name': item_name, 'type': t_type, 'quantity': t_qty})

        # Revert Stock
        if item:
            if t.transaction_type in INV_TX_TYPES_USAGE_WASTE:
                item.current_stock += t.quantity
            else: # Purchase, Adjustment
                item.current_stock -= t.quantity

        db.session.delete(t)
        safe_commit()
        flash(f"Transaction deleted. Stock reverted.", "info")
        return redirect(url_for('inventory'))

    @app.route('/inventory/edit/<int:id>', methods=['POST'])
    @login_required
    @dept_required('Farm')
    def edit_inventory_item(id):
        item = InventoryItem.query.get_or_404(id)

        if request.form.get('delete') == '1':
            item_name = item.name
            log_user_activity(current_user.id, 'Delete', 'InventoryItem', id, details={'name': item_name})
            db.session.delete(item)
            safe_commit()
            flash('Item deleted.', 'info')
            return redirect(url_for('inventory'))

        old_data = {
            'name': item.name,
            'type': item.type,
            'unit': item.unit,
            'min_stock_level': item.min_stock_level,
            'doses_per_unit': item.doses_per_unit,
            'batch_number': item.batch_number,
            'expiry_date': item.expiry_date.strftime('%Y-%m-%d') if item.expiry_date else None
        }

        item.name = request.form.get('name')
        item.type = request.form.get('type')
        item.unit = request.form.get('unit')
        item.min_stock_level = float(request.form.get('min_stock_level') or 0)

        doses = request.form.get('doses_per_unit')
        item.doses_per_unit = int(doses) if doses else None

        item.batch_number = request.form.get('batch_number')

        exp = request.form.get('expiry_date')
        if exp:
            item.expiry_date = datetime.strptime(exp, '%Y-%m-%d').date()
        else:
            item.expiry_date = None

        new_data = {
            'name': item.name,
            'type': item.type,
            'unit': item.unit,
            'min_stock_level': item.min_stock_level,
            'doses_per_unit': item.doses_per_unit,
            'batch_number': item.batch_number,
            'expiry_date': item.expiry_date.strftime('%Y-%m-%d') if item.expiry_date else None
        }

        changes = {k: {'old': old_data[k], 'new': new_data[k]} for k in old_data if old_data[k] != new_data[k]}
        if changes:
            log_user_activity(current_user.id, 'Edit', 'InventoryItem', item.id, details=changes)

        safe_commit()
        flash('Item updated.', 'success')
        return redirect(url_for('inventory'))

    @app.route('/inventory/transaction', methods=['POST'])
    @login_required
    @dept_required('Farm')
    def inventory_transaction():
        item_id = int(request.form.get('inventory_item_id'))
        type_ = request.form.get('transaction_type')
        qty = float(request.form.get('quantity') or 0)
        date_str = request.form.get('transaction_date')
        date_val = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
        notes = request.form.get('notes')

        if qty <= 0:
            flash('Quantity must be positive.', 'danger')
            return redirect(url_for('inventory'))

        item = InventoryItem.query.get_or_404(item_id)

        if type_ in INV_TX_TYPES_USAGE_WASTE:
            item.current_stock -= qty
        else: # Purchase, Adjustment
            item.current_stock += qty

        if item.current_stock < 0:
            flash(f'Warning: Stock for {item.name} went negative.', 'warning')

        t = InventoryTransaction(
            inventory_item_id=item.id,
            transaction_type=type_,
            quantity=qty,
            transaction_date=date_val,
            notes=notes
        )
        db.session.add(t)
        try:
            db.session.flush()
            log_user_activity(current_user.id, 'Add', 'InventoryTransaction', t.id, details={'item_name': item.name, 'type': type_, 'quantity': qty})
            safe_commit()
            flash('Transaction recorded.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error recording transaction: {str(e)}', 'danger')

        return redirect(url_for('inventory'))

    @app.route('/inventory/add', methods=['POST'])
    @login_required
    @dept_required('Farm')
    def add_inventory_item():
        name = request.form.get('name')
        type_ = request.form.get('type')
        unit = request.form.get('unit')
        stock = float(request.form.get('current_stock') or 0)
        min_stock = float(request.form.get('min_stock_level') or 0)
        doses = int(request.form.get('doses_per_unit') or 0) if type_ == 'Vaccine' else None
        batch = request.form.get('batch_number')
        exp_str = request.form.get('expiry_date')
        exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date() if exp_str else None

        item = InventoryItem(
            name=name, type=type_, unit=unit, current_stock=stock,
            min_stock_level=min_stock, doses_per_unit=doses,
            batch_number=batch, expiry_date=exp_date
        )
        db.session.add(item)
        db.session.flush()

        log_user_activity(current_user.id, 'Add', 'InventoryItem', item.id, details={'name': name, 'type': type_, 'initial_stock': stock})

        safe_commit()

        if stock > 0:
            t = InventoryTransaction(
                inventory_item_id=item.id,
                transaction_type='Purchase',
                quantity=stock,
                transaction_date=date.today(),
                notes='Initial Stock'
            )
            db.session.add(t)
            safe_commit()

        flash(f'Added {name} to inventory.', 'success')
        return redirect(url_for('inventory'))

    @app.route('/inventory')
    @login_required
    @dept_required('Farm')
    def inventory():
        items = InventoryItem.query.order_by(InventoryItem.name).all()
        transactions = InventoryTransaction.query.order_by(InventoryTransaction.transaction_date.desc(), InventoryTransaction.id.desc()).limit(50).all()

        # Monthly Summary
        today = date.today()
        start_of_month = date(today.year, today.month, 1)

        month_txs = InventoryTransaction.query.filter(InventoryTransaction.transaction_date >= start_of_month).all()

        summary_map = {}
        for t in month_txs:
            if t.inventory_item_id not in summary_map:
                summary_map[t.inventory_item_id] = {'purchase': 0, 'usage': 0, 'waste': 0}

            type_key = t.transaction_type.lower()
            if type_key in summary_map[t.inventory_item_id]:
                summary_map[t.inventory_item_id][type_key] += t.quantity

        summary_list = []
        for item in items:
            s = summary_map.get(item.id, {'purchase': 0, 'usage': 0, 'waste': 0})
            summary_list.append({
                'name': item.name,
                'purchase': round(s['purchase'], 2),
                'usage': round(s['usage'], 2),
                'waste': round(s['waste'], 2)
            })

        return render_template('inventory.html', items=items, transactions=transactions, summary=summary_list, current_month=today.strftime('%B %Y'), today=today)

    @app.route('/daily_log/<int:id>/edit', methods=['GET', 'POST'])
    @login_required
    @dept_required('Farm')
    def edit_daily_log(id):
        log = DailyLog.query.get_or_404(id)
        breadcrumbs = [{'name': 'Dashboard', 'url': url_for('index')}, {'name': f'Flock {log.flock.flock_id}', 'url': url_for('view_flock', id=log.flock.id)}, {'name': 'Edit Daily Log', 'url': None}]

        if request.method == 'POST':
            # Handle Vaccines
            vaccine_present_ids = request.form.getlist('vaccine_present_ids')
            vaccine_completed_ids = request.form.getlist('vaccine_completed_ids')

            # Convert to integers for precise DB query
            int_vaccine_present_ids = []
            for vid in vaccine_present_ids:
                try:
                    int_vaccine_present_ids.append(int(vid))
                except ValueError:
                    pass

            if int_vaccine_present_ids:
                # Optimize N+1 Query: Bulk fetch instead of individual gets
                vaccines = Vaccine.query.filter(Vaccine.id.in_(int_vaccine_present_ids)).all()
                for vac in vaccines:
                    if vac.flock_id == log.flock_id:
                        if str(vac.id) in vaccine_completed_ids:
                            vac.actual_date = log.date
                        elif vac.actual_date == log.date:
                            vac.actual_date = None

            # Handle Multiple Medications
            med_names = request.form.getlist('med_drug_name[]')
            med_inventory_ids = request.form.getlist('med_inventory_id[]')
            med_dosages = request.form.getlist('med_dosage[]')
            med_amounts = request.form.getlist('med_amount_used[]')
            med_amount_qtys = request.form.getlist('med_amount_qty[]')
            med_start_dates = request.form.getlist('med_start_date[]')
            med_end_dates = request.form.getlist('med_end_date[]')
            med_remarks = request.form.getlist('med_remarks[]')

            # Batch fetch inventory items
            unique_inv_ids = {int(iid) for iid in med_inventory_ids if iid and iid.isdigit()}
            inventory_items_dict = {}
            if unique_inv_ids:
                items = InventoryItem.query.filter(InventoryItem.id.in_(unique_inv_ids)).all()
                inventory_items_dict = {item.id: item for item in items}

            for i, name_val in enumerate(med_names):
                inv_id_val = med_inventory_ids[i] if i < len(med_inventory_ids) else None

                item_name = name_val
                inv_id = None
                if inv_id_val and inv_id_val.isdigit():
                    inv_id = int(inv_id_val)
                    item = inventory_items_dict.get(inv_id)
                    if item: item_name = item.name

                if not item_name and not inv_id:
                    continue

                s_date = log.date
                s_date_val = med_start_dates[i] if i < len(med_start_dates) else None
                if s_date_val:
                    try:
                        s_date = datetime.strptime(s_date_val, '%Y-%m-%d').date()
                    except: pass

                e_date = None
                e_date_val = med_end_dates[i] if i < len(med_end_dates) else None
                if e_date_val:
                    try:
                        e_date = datetime.strptime(e_date_val, '%Y-%m-%d').date()
                    except: pass

                qty = None
                try:
                    qty_val = med_amount_qtys[i] if i < len(med_amount_qtys) else None
                    if qty_val: qty = float(qty_val)
                except: pass

                med = Medication(
                    flock_id=log.flock_id,
                    drug_name=item_name,
                    inventory_item_id=inv_id,
                    dosage=med_dosages[i] if i < len(med_dosages) else '',
                    amount_used=med_amounts[i] if i < len(med_amounts) else '',
                    amount_used_qty=qty,
                    start_date=s_date,
                    end_date=e_date,
                    remarks=med_remarks[i] if i < len(med_remarks) else ''
                )
                db.session.add(med)

                if inv_id and qty and qty > 0:
                    inv_item = inventory_items_dict.get(inv_id)
                    if inv_item:
                        inv_item.current_stock -= qty
                        t = InventoryTransaction(
                            inventory_item_id=inv_id,
                            transaction_type='Usage',
                            quantity=qty,
                            transaction_date=s_date,
                            notes=f'Used in Daily Log: {log.flock.flock_id}'
                        )
                        db.session.add(t)

            try:
                update_log_from_request(log, request)
            except ValueError as e:
                db.session.rollback()
                if request.headers.get('Accept') == 'application/json':
                    return jsonify({'success': False, 'error': str(e)}), 400
                flash(str(e), 'danger')
                return redirect(url_for('edit_daily_log', id=id))

            # Automatic Production Trigger
            if log.eggs_collected > 0 and not log.flock.start_of_lay_date:
                log.flock.start_of_lay_date = log.date
                flash(f"First egg detected! Production tracking started for {log.flock.flock_id} from {log.date}.", "info")

            try:
                safe_commit()
                recalculate_flock_inventory(log.flock_id)
                if request.headers.get('Accept') == 'application/json':
                    house_status = check_daily_log_completion(log.flock.farm_id, log.date)
                    return jsonify({
                        'success': True,
                        'message': 'Log updated successfully.',
                        'houses': house_status,
                        'date': log.date.strftime('%Y-%m-%d')
                    })
                flash('Log updated successfully.', 'success')
                return redirect(url_for('edit_daily_log', id=id))
            except Exception as e:
                db.session.rollback()
                if request.headers.get('Accept') == 'application/json':
                    return jsonify({'success': False, 'error': f"Database Error: {str(e)}"}), 500
                flash(f"Database Error: {str(e)}", 'danger')
                return redirect(url_for('edit_daily_log', id=id))

        feed_codes = FeedCode.query.order_by(FeedCode.code.asc()).all()

        vaccines_due = []
        target_flock_id = log.flock_id
        target_date = log.date

        all_vacs = Vaccine.query.filter_by(flock_id=target_flock_id).all()
        lookahead = target_date + timedelta(days=7)

        for v in all_vacs:
            is_relevant = False
            if v.actual_date == target_date:
                is_relevant = True
            elif v.actual_date is None:
                if v.est_date and v.est_date <= lookahead:
                    is_relevant = True

            if is_relevant:
                vaccines_due.append(v)

        vaccines_due.sort(key=lambda x: x.est_date or date.max)

        medication_inventory = InventoryItem.query.filter_by(type='Medication').order_by(InventoryItem.name).all()

        return render_template('daily_log_form.html', log=log, houses=[log.flock.house], feed_codes=feed_codes, vaccines_due=vaccines_due, medication_inventory=medication_inventory, breadcrumbs=breadcrumbs)

    @app.route('/daily_log', methods=['GET', 'POST'])
    @login_required
    @dept_required('Farm')
    def daily_log():
        if request.method == 'POST':
            house_id = request.form.get('house_id')
            date_str = request.form.get('date')

            flock = Flock.query.filter_by(house_id=house_id, status='Active').first()
            if not flock:
                if request.headers.get('Accept') == 'application/json':
                    return jsonify({'success': False, 'error': 'No active flock found for this house.'}), 400
                flash('Error: No active flock found for this house.', 'danger')
                return redirect(url_for('daily_log'))

            try:
                log_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                if request.headers.get('Accept') == 'application/json':
                    return jsonify({'success': False, 'error': 'Invalid date format.'}), 400
                flash('Error: Invalid date format.', 'danger')
                return redirect(url_for('daily_log'))

            # Gap Detection Logic
            from markupsafe import Markup
            if log_date > flock.intake_date:
                # We need to check all dates from intake_date to log_date - 1
                # We can find the missing dates by querying existing logs in that range
                existing_logs_dates = [
                    d[0] for d in db.session.query(DailyLog.date).filter(
                        DailyLog.flock_id == flock.id,
                        DailyLog.date >= flock.intake_date,
                        DailyLog.date < log_date
                    ).all()
                ]

                # Find the first missing date
                current_check_date = flock.intake_date
                missing_date = None
                while current_check_date < log_date:
                    if current_check_date not in existing_logs_dates:
                        missing_date = current_check_date
                        break
                    current_check_date += timedelta(days=1)

                if missing_date:
                    missing_date_str = missing_date.strftime('%Y-%m-%d')
                    missing_url = url_for('daily_log', house_id=house_id, date=missing_date_str)
                    error_msg = f'Error: Data Gap Detected. Please <a href="{missing_url}" class="alert-link">complete the missing daily log for {missing_date_str}</a> before proceeding.'

                    if request.headers.get('Accept') == 'application/json':
                        return jsonify({'success': False, 'error': error_msg}), 400

                    flash(Markup(error_msg), 'danger')
                    return redirect(url_for('daily_log', house_id=house_id, date=date_str))

            existing_log = DailyLog.query.filter_by(flock_id=flock.id, date=log_date).first()

            if existing_log:
                log = existing_log
                flash_msg = 'Daily Log updated successfully!'
            else:
                log = DailyLog(
                    flock_id=flock.id,
                    date=log_date,                body_weight_male=0,
                    body_weight_female=0
                )
                db.session.add(log)
                flash_msg = 'Daily Log submitted successfully!'

            log.flock = flock
            db.session.add(log)

            try:
                update_log_from_request(log, request)
            except ValueError as e:
                db.session.rollback()
                if request.headers.get('Accept') == 'application/json':
                    return jsonify({'success': False, 'error': str(e)}), 400
                flash(str(e), 'danger')
                return redirect(url_for('daily_log', house_id=house_id, date=date_str))

            # Automatic Production Trigger
            if log.eggs_collected > 0 and not flock.start_of_lay_date:
                flock.start_of_lay_date = log.date
                flash(f"First egg detected! Production tracking started for {flock.flock_id} from {log.date}.", "info")

            # Handle Vaccines (Mark as Completed)
            vaccine_present_ids = request.form.getlist('vaccine_present_ids')
            vaccine_completed_ids = request.form.getlist('vaccine_completed_ids')

            # Convert to integers for precise DB query
            int_vaccine_present_ids = []
            for vid in vaccine_present_ids:
                try:
                    int_vaccine_present_ids.append(int(vid))
                except ValueError:
                    pass

            if int_vaccine_present_ids:
                # Optimize N+1 Query: Bulk fetch instead of individual gets
                vaccines = Vaccine.query.filter(Vaccine.id.in_(int_vaccine_present_ids)).all()
                for vac in vaccines:
                    if vac.flock_id == flock.id:
                        if str(vac.id) in vaccine_completed_ids:
                            vac.actual_date = log_date
                        elif vac.actual_date == log_date:
                            # Only unset if it was set to THIS date (don't clear history if logic changes)
                            vac.actual_date = None

            # Handle Multiple Medications
            med_names = request.form.getlist('med_drug_name[]')
            med_inventory_ids = request.form.getlist('med_inventory_id[]')
            med_dosages = request.form.getlist('med_dosage[]')
            med_amounts = request.form.getlist('med_amount_used[]') # Legacy text
            med_amount_qtys = request.form.getlist('med_amount_qty[]') # New numeric
            med_start_dates = request.form.getlist('med_start_date[]')
            med_end_dates = request.form.getlist('med_end_date[]')
            med_remarks = request.form.getlist('med_remarks[]')

            # Batch fetch inventory items
            unique_inv_ids = {int(iid) for iid in med_inventory_ids if iid and iid.isdigit()}
            inventory_items_dict = {}
            if unique_inv_ids:
                items = InventoryItem.query.filter(InventoryItem.id.in_(unique_inv_ids)).all()
                inventory_items_dict = {item.id: item for item in items}

            for i, name_val in enumerate(med_names):
                inv_id_val = med_inventory_ids[i] if i < len(med_inventory_ids) else None

                # Determine Name: Inventory Name > Manual Name
                item_name = name_val
                inv_id = None

                if inv_id_val and inv_id_val.isdigit():
                    inv_id = int(inv_id_val)
                    item = inventory_items_dict.get(inv_id)
                    if item: item_name = item.name

                if not item_name and not inv_id:
                    continue

                s_date = log_date
                s_date_val = med_start_dates[i] if i < len(med_start_dates) else None
                if s_date_val:
                    try:
                        s_date = datetime.strptime(s_date_val, '%Y-%m-%d').date()
                    except: pass

                e_date = None
                e_date_val = med_end_dates[i] if i < len(med_end_dates) else None
                if e_date_val:
                    try:
                        e_date = datetime.strptime(e_date_val, '%Y-%m-%d').date()
                    except: pass

                qty = None
                try:
                    qty_val = med_amount_qtys[i] if i < len(med_amount_qtys) else None
                    if qty_val: qty = float(qty_val)
                except: pass

                med = Medication(
                    flock_id=flock.id,
                    drug_name=item_name,
                    inventory_item_id=inv_id,
                    dosage=med_dosages[i] if i < len(med_dosages) else '',
                    amount_used=med_amounts[i] if i < len(med_amounts) else '',
                    amount_used_qty=qty,
                    start_date=s_date,
                    end_date=e_date,
                    remarks=med_remarks[i] if i < len(med_remarks) else ''
                )
                db.session.add(med)

                # Auto-Deduct from Inventory
                if inv_id and qty and qty > 0:
                    inv_item = inventory_items_dict.get(inv_id)
                    if inv_item:
                        inv_item.current_stock -= qty
                        t = InventoryTransaction(
                            inventory_item_id=inv_id,
                            transaction_type='Usage',
                            quantity=qty,
                            transaction_date=s_date,
                            notes=f'Used in Daily Log: {flock.flock_id}'
                        )
                        db.session.add(t)

            try:
                safe_commit()
                recalculate_flock_inventory(flock.id)
                if request.headers.get('Accept') == 'application/json':
                    house_status = check_daily_log_completion(flock.farm_id, log_date)
                    return jsonify({
                        'success': True,
                        'message': flash_msg,
                        'houses': house_status,
                        'date': date_str
                    })
                flash(flash_msg, 'success')
                return redirect(url_for('daily_log', house_id=house_id, date=date_str))
            except Exception as e:
                db.session.rollback()
                if request.headers.get('Accept') == 'application/json':
                    return jsonify({'success': False, 'error': f"Database Error: {str(e)}"}), 500
                flash(f"Database Error: {str(e)}", 'danger')
                return redirect(url_for('daily_log', house_id=house_id, date=date_str))

        active_flocks = Flock.query.options(joinedload(Flock.house)).filter_by(status='Active').all()
        active_houses = [f.house for f in active_flocks]

        flock_phases = {}

        for f in active_flocks:
            flock_phases[f.house_id] = f.phase

        feed_codes = FeedCode.query.order_by(FeedCode.code.asc()).all()

        selected_house_id = request.args.get('house_id')
        selected_date_str = request.args.get('date')
        log = None
        vaccines_due = []

        # If log exists, we use log.flock.id. If not, we try selected_house_id.
        target_flock_id = None
        target_date = date.today()

        if selected_house_id and selected_date_str:
            try:
                 h_id = int(selected_house_id)
                 d_obj = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
                 target_date = d_obj

                 target_flock = Flock.query.filter_by(house_id=h_id, status='Active').first()
                 if target_flock:
                     target_flock_id = target_flock.id
                     log = DailyLog.query.filter_by(flock_id=target_flock.id, date=d_obj).first()
            except:
                 pass
        elif log:
            target_flock_id = log.flock_id
            target_date = log.date

        if target_flock_id:
            # Fetch relevant vaccines
            # Criteria: Actual Date is target_date OR (Actual is None AND Est Date <= target_date + 7)
            all_vacs = Vaccine.query.filter_by(flock_id=target_flock_id).all()
            lookahead = target_date + timedelta(days=7)

            for v in all_vacs:
                is_relevant = False
                if v.actual_date == target_date:
                    is_relevant = True
                elif v.actual_date is None:
                    if v.est_date and v.est_date <= lookahead:
                        is_relevant = True

                if is_relevant:
                    vaccines_due.append(v)

            # Sort by est_date
            vaccines_due.sort(key=lambda x: x.est_date or date.max)

        # Fetch Inventory Items (Medications)
        medication_inventory = InventoryItem.query.filter_by(type='Medication').order_by(InventoryItem.name).all()

        breadcrumbs = [{'name': 'Dashboard', 'url': url_for('index')}, {'name': 'Daily Log', 'url': None}]

        return render_template('daily_log_form.html',
                               houses=active_houses,
                               flock_phases_json=json.dumps(flock_phases),
                               feed_codes=feed_codes,
                               log=log,
                               selected_house_id=int(selected_house_id) if selected_house_id and selected_house_id.isdigit() else None,
                               selected_date=selected_date_str,
                               vaccines_due=vaccines_due,
                               medication_inventory=medication_inventory,
                               breadcrumbs=breadcrumbs)

    @app.route('/flock/<int:id>/charts')
    @login_required
    @dept_required('Farm')
    def flock_charts(id):
        flock = Flock.query.options(joinedload(Flock.house)).filter_by(id=id).first_or_404()
        return render_template('flock_charts.html', flock=flock)

    @app.route('/flock/<int:id>/spreadsheet')
    @login_required
    @dept_required('Farm')
    def flock_spreadsheet(id):
        if not current_user.role == 'Admin':
            flash('Access Denied: Admin only.', 'danger')
            return redirect(url_for('view_flock', id=id))

        flock = db.session.get(Flock, id)
        if not flock:
            flash('Flock not found', 'danger')
            return redirect(url_for('index'))

        # Load all logs for this flock
        logs = DailyLog.query.options(joinedload(DailyLog.partition_weights), joinedload(DailyLog.photos), joinedload(DailyLog.clinical_notes_list)).filter_by(flock_id=id).order_by(DailyLog.date.asc()).all()

        # Enrich with standards (for benchmarks)
        standards_list = Standard.query.all()
        standards_by_week = {getattr(s, 'week'): s for s in standards_list if hasattr(s, 'week')}
        standards_by_prod_week = {s.production_week: s for s in standards_list}

        # Fetch Global Standard for hatching egg %
        gs = GlobalStandard.query.first()
        std_hatching_egg_pct = gs.std_hatching_egg_pct if gs and gs.std_hatching_egg_pct is not None else 96.0

        # Fetch Feed Codes
        feed_codes = FeedCode.query.order_by(FeedCode.code.asc()).all()
        feed_code_options = [fc.code for fc in feed_codes]

        spreadsheet_data = []

        spreadsheet_data = generate_spreadsheet_data(flock, logs, standards_by_week, standards_by_prod_week)

        return render_template('flock_spreadsheet_modern.html', flock=flock, spreadsheet_data=spreadsheet_data, feed_codes=feed_code_options)

    @app.route('/flock/<int:id>')
    @login_required
    @dept_required('Farm')
    def view_flock(id):
        active_flocks = Flock.query.options(joinedload(Flock.house)).filter_by(status='Active').all()

        if active_flocks:
                active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else ''))

        flock = Flock.query.options(joinedload(Flock.house)).filter_by(id=id).first_or_404()
        logs = DailyLog.query.options(joinedload(DailyLog.partition_weights), joinedload(DailyLog.photos), joinedload(DailyLog.clinical_notes_list)).filter_by(flock_id=id).order_by(DailyLog.date.asc()).all()

        # --- Health Analytics ---
        health_events = analyze_health_events(logs)

        gs = GlobalStandard.query.first()
        if not gs:
            gs = GlobalStandard()
            db.session.add(gs)
            safe_commit()

        # --- Standards Setup ---
        all_standards = Standard.query.all()
        std_map = {getattr(s, 'week'): s for s in all_standards if hasattr(s, 'week')} # Biological Age Map
        prod_std_map = {getattr(s, 'production_week'): s for s in all_standards if hasattr(s, 'production_week') and getattr(s, 'production_week')} # Production Week Map

        # --- Fetch Hatch Data ---
        hatch_records = Hatchability.query.filter_by(flock_id=id).order_by(Hatchability.setting_date.desc()).all()

        # --- Metrics Engine ---
        daily_stats = enrich_flock_data(flock, logs, hatch_records)

        # --- Calculate Summary Tab Data ---
        summary_dashboard, summary_table = calculate_flock_summary(flock, daily_stats)

        # Inject Standards
        for d in daily_stats:
            # Production Metrics (Egg Prod, Weight, Hatch) -> Use Production Week
            prod_std = None
            if d.get('production_week'):
                prod_std = prod_std_map.get(d['production_week'])

            d['std_egg_prod'] = (prod_std.std_egg_prod if prod_std and prod_std.std_egg_prod is not None else 0.0)
            d['std_hatching_egg_pct'] = (prod_std.std_hatching_egg_pct if prod_std and prod_std.std_hatching_egg_pct is not None else 0.0)
            # Add other production standards if needed by template

        weekly_stats = aggregate_weekly_metrics(daily_stats)

        for ws in weekly_stats:
            prod_std = None
            if ws.get('production_week'):
                prod_std = prod_std_map.get(ws['production_week'])

            ws['std_egg_prod'] = (prod_std.std_egg_prod if prod_std and prod_std.std_egg_prod is not None else 0.0)
            ws['std_hatching_egg_pct'] = (prod_std.std_hatching_egg_pct if prod_std and prod_std.std_hatching_egg_pct is not None else 0.0)

        medications = Medication.query.filter_by(flock_id=id).all()
        vacs = Vaccine.query.filter_by(flock_id=id).filter(Vaccine.actual_date != None).all()

        # 1. Enriched Logs (For Table)
        enriched_logs = []

        def scale_pct(val):
            if val is None: return None
            if 0 < val <= 1.0: return val * 100.0
            return val

        for d in daily_stats:
            log = d['log']

            # View Specific: Lighting
            lighting_hours = 0
            if log.light_on_time and log.light_off_time:
                try:
                    fmt = '%H:%M'
                    t1 = datetime.strptime(log.light_on_time, fmt)
                    t2 = datetime.strptime(log.light_off_time, fmt)
                    diff = (t2 - t1).total_seconds() / 3600
                    if diff < 0: diff += 24
                    lighting_hours = round(diff, 1)
                except: pass

            # View Specific: Meds
            active_meds = []
            for m in medications:
                if m.start_date <= log.date:
                    if m.end_date is None or m.end_date >= log.date:
                        active_meds.append(m.drug_name)
            meds_str = ", ".join(active_meds)

            cleanup_duration_mins = None
            if log.feed_cleanup_start and log.feed_cleanup_end:
                try:
                    cleanup_duration_mins = calculate_feed_cleanup_duration(log.feed_cleanup_start, log.feed_cleanup_end)
                except Exception:
                    pass
            feed_cleanup_hours = round(cleanup_duration_mins / 60.0, 1) if cleanup_duration_mins else None

            enriched_logs.append({
                'log': log,
                'stock_male': d.get('stock_male_prod_end', 0) + d.get('stock_male_hosp_end', 0),
                'stock_female': d.get('stock_female_prod_end', 0) + d.get('stock_female_hosp_end', 0),
                'lighting_hours': lighting_hours,
                'medications': meds_str,
                'egg_prod_pct': d['egg_prod_pct'],
                'total_feed': d['feed_total_kg'],
                'feed_cleanup_hours': feed_cleanup_hours,
                'egg_data': {
                    'jumbo': d['cull_eggs_jumbo'],
                    'jumbo_pct': d['cull_eggs_jumbo_pct'],
                    'small': d['cull_eggs_small'],
                    'small_pct': d['cull_eggs_small_pct'],
                    'crack': d['cull_eggs_crack'],
                    'crack_pct': d['cull_eggs_crack_pct'],
                    'abnormal': d['cull_eggs_abnormal'],
                    'abnormal_pct': d['cull_eggs_abnormal_pct'],
                    'hatching': d['hatch_eggs'],
                    'hatching_pct': d['hatch_egg_pct'],
                    'total_culls': d['cull_eggs_total'],
                    'total_culls_pct': d['cull_eggs_pct']
                }
            })

        # 2. Weekly Data (For Table)
        weekly_data = []
        for ws in weekly_stats:
            # Notes formatting
            note_str = " | ".join(ws['notes'])

            w_item = {
                'week': ws['week'],
                'mortality_male': ws['mortality_male'],
                'mortality_female': ws['mortality_female'],
                'culls_male': ws['culls_male'],
                'culls_female': ws['culls_female'],
                'eggs': ws['eggs_collected'],
                'hatch_eggs_sum': ws['hatch_eggs'],
                'cull_eggs_total': ws['cull_eggs_jumbo'] + ws['cull_eggs_small'] + ws['cull_eggs_crack'] + ws['cull_eggs_abnormal'],

                # Derived
                'mort_pct_m': ws['mortality_male_pct'],
                'mort_pct_f': ws['mortality_female_pct'],
                'cull_pct_m': ws['culls_male_pct'],
                'cull_pct_f': ws['culls_female_pct'],
                'egg_prod_pct': ws['egg_prod_pct'],
                'hatching_egg_pct': ws['hatch_egg_pct'],
                'cull_eggs_jumbo': ws['cull_eggs_jumbo'],
                'cull_eggs_jumbo_pct': ws['cull_eggs_jumbo_pct'] * 100 if ws.get('cull_eggs_jumbo_pct') else 0,
                'cull_eggs_small': ws['cull_eggs_small'],
                'cull_eggs_small_pct': ws['cull_eggs_small_pct'] * 100 if ws.get('cull_eggs_small_pct') else 0,
                'cull_eggs_crack': ws['cull_eggs_crack'],
                'cull_eggs_crack_pct': ws['cull_eggs_crack_pct'] * 100 if ws.get('cull_eggs_crack_pct') else 0,
                'cull_eggs_abnormal': ws['cull_eggs_abnormal'],
                'cull_eggs_abnormal_pct': ws['cull_eggs_abnormal_pct'] * 100 if ws.get('cull_eggs_abnormal_pct') else 0,

                'avg_bw_male': round_to_whole(ws['body_weight_male']),
                'avg_bw_female': round_to_whole(ws['body_weight_female']),

                # Additional for Charts
                'avg_bw_male_std': 0, # Placeholder if needed, or calc
                'avg_bw_female_std': 0,
                'avg_unif_male': ws['uniformity_male'],
                'avg_unif_female': ws['uniformity_female'],
                'partition_avgs': {}, # Not strictly used in table unless drilled down

                'notes': ws['notes'],
                'photos': ws['photos']
            }
            weekly_data.append(w_item)

        # 3. Chart Data (Daily)
        chart_data = {
            'dates': [d['date'].strftime('%Y-%m-%d') for d in daily_stats],
            'ages': [d['log'].age_week_day for d in daily_stats],
            'mortality_cum_male': [round(d['mortality_cum_male_pct'], 2) for d in daily_stats],
            'mortality_cum_female': [round(d['mortality_cum_female_pct'], 2) for d in daily_stats],
            'mortality_daily_male': [round(d['mortality_male_pct'], 2) for d in daily_stats],
            'mortality_daily_female': [round(d['mortality_female_pct'], 2) for d in daily_stats],
            'culls_daily_male': [round(d['culls_male_pct'], 2) for d in daily_stats],
            'culls_daily_female': [round(d['culls_female_pct'], 2) for d in daily_stats],
            'egg_prod': [round(d['egg_prod_pct'], 2) for d in daily_stats],
            'std_egg_prod': [round(d['std_egg_prod'], 2) for d in daily_stats],
            'hatch_egg_pct': [round(d['hatch_egg_pct'], 2) for d in daily_stats],
            'std_hatching_egg_pct': [round(d['std_hatching_egg_pct'], 2) for d in daily_stats],
            'cull_eggs_jumbo_pct': [round(d['cull_eggs_jumbo_pct'], 2) for d in daily_stats],
            'cull_eggs_small_pct': [round(d['cull_eggs_small_pct'], 2) for d in daily_stats],
            'cull_eggs_crack_pct': [round(d['cull_eggs_crack_pct'], 2) for d in daily_stats],
            'cull_eggs_abnormal_pct': [round(d['cull_eggs_abnormal_pct'], 2) for d in daily_stats],
            'male_ratio': [round(d['male_ratio_stock'], 2) if d['male_ratio_stock'] else 0 for d in daily_stats],
            'bw_male_std': [d['log'].standard_bw_male if d['log'].standard_bw_male > 0 else None for d in daily_stats],
            'bw_female_std': [d['log'].standard_bw_female if d['log'].standard_bw_female > 0 else None for d in daily_stats],
            'unif_male': [scale_pct(d['uniformity_male']) if d['uniformity_male'] > 0 else None for d in daily_stats],
            'unif_female': [scale_pct(d['uniformity_female']) if d['uniformity_female'] > 0 else None for d in daily_stats],

            # Raw BW for charts (None if 0)
            'bw_f': [d['body_weight_female'] if d['body_weight_female'] > 0 else None for d in daily_stats],
            'bw_m': [d['body_weight_male'] if d['body_weight_male'] > 0 else None for d in daily_stats],

            'water_per_bird': [round(d['water_per_bird'], 1) if d['water_per_bird'] >= 0 else None for d in daily_stats],
            'water_feed_ratio': [round(d.get('water_feed_ratio'), 2) if d.get('water_feed_ratio') is not None and d.get('water_feed_ratio') >= 0 else None for d in daily_stats],
            'feed_male_gp_bird': [round(d['feed_male_gp_bird'], 1) for d in daily_stats],
            'feed_female_gp_bird': [round(d['feed_female_gp_bird'], 1) for d in daily_stats],
            'flushing': [d['log'].flushing for d in daily_stats],

            # Legacy Partitions from Log
            'bw_male_p1': [d['log'].bw_male_p1 if d['log'].bw_male_p1 > 0 else None for d in daily_stats],
            'bw_male_p2': [d['log'].bw_male_p2 if d['log'].bw_male_p2 > 0 else None for d in daily_stats],
            'bw_female_p1': [d['log'].bw_female_p1 if d['log'].bw_female_p1 > 0 else None for d in daily_stats],
            'bw_female_p2': [d['log'].bw_female_p2 if d['log'].bw_female_p2 > 0 else None for d in daily_stats],
            'bw_female_p3': [d['log'].bw_female_p3 if d['log'].bw_female_p3 > 0 else None for d in daily_stats],
            'bw_female_p4': [d['log'].bw_female_p4 if d['log'].bw_female_p4 > 0 else None for d in daily_stats],

            'notes': [],
            'medication_active': [],
            'medication_names': []
        }

        # Fill dynamic partitions and notes
        for i in range(1, 9):
            chart_data[f'bw_M{i}'] = []
            chart_data[f'bw_F{i}'] = []

        for d in daily_stats:
            log = d['log']
            p_map = {pw.partition_name: pw.body_weight for pw in log.partition_weights}

            for i in range(1, 9):
                val_m = p_map.get(f'M{i}', 0)
                if val_m == 0 and i <= 2: val_m = getattr(log, f'bw_male_p{i}', 0)
                chart_data[f'bw_M{i}'].append(val_m if val_m > 0 else None)

                val_f = p_map.get(f'F{i}', 0)
                if val_f == 0 and i <= 4: val_f = getattr(log, f'bw_female_p{i}', 0)
                chart_data[f'bw_F{i}'].append(val_f if val_f > 0 else None)

            note_obj = None

            # Construct Note
            note_parts = []
            if log.flushing: note_parts.append("[FLUSHING]")
            if log.clinical_notes: note_parts.append(log.clinical_notes)

            # Meds
            active_meds = [m.drug_name for m in medications if m.start_date <= log.date and (m.end_date is None or m.end_date >= log.date)]
            chart_data['medication_active'].append(len(active_meds) > 0)
            chart_data['medication_names'].append(", ".join(active_meds) if active_meds else "")

            # User requested to remove medication from notes, so we don't append to note_parts
            # if active_meds: note_parts.append("Meds: " + ", ".join(active_meds))

            # Vacs
            done_vacs = [v.vaccine_name for v in vacs if v.actual_date == log.date]
            if done_vacs: note_parts.append("Vac: " + ", ".join(done_vacs))

            # Main Photos (note_id is None)
            main_photos = [p for p in log.photos if p.note_id is None]

            # Extra Notes
            extra_notes = []
            if log.clinical_notes_list:
                for n in log.clinical_notes_list:
                    n_photos = []
                    for p in n.photos:
                        n_photos.append({
                            'url': url_for('uploaded_file', filename=os.path.basename(p.file_path)),
                            'name': p.original_filename or 'Photo'
                        })
                    extra_notes.append({
                        'caption': n.caption,
                        'photos': n_photos
                    })

            has_any_data = (note_parts or main_photos or extra_notes)

            if has_any_data:
                main_photo_list = []
                for p in main_photos:
                    main_photo_list.append({
                        'url': url_for('uploaded_file', filename=os.path.basename(p.file_path)),
                        'name': p.original_filename or 'Photo'
                    })

                note_obj = {
                    'note': " | ".join(note_parts), # Kept for backward compat in tooltips
                    'main_note': " | ".join(note_parts),
                    'main_photos': main_photo_list,
                    'extra_notes': extra_notes,
                    'photos': main_photo_list # Fallback for legacy views
                }

            chart_data['notes'].append(note_obj)

        # 4. Chart Data (Weekly)
        # Calculate Cumulative Mortality for Weekly points manually as metrics.py aggregates per week (independent sums)
        cum_mort_m_agg = 0
        cum_mort_f_agg = 0
        start_m = flock.intake_male or 1
        start_f = flock.intake_female or 1

        # Check if we are in production phase to use prod start?
        # metrics.py handles this per week if we query it right, but here we just iterate
        # Actually metrics.py `enrich` resets cum sum on phase switch.
        # We should grab the last cumulative value of the week from daily stats?
        # Yes, much safer. But daily stats are flattened.
        # Let's just sum up the weekly deaths.
        # NOTE: If phase switch happened mid-week, the cumulative logic is tricky.
        # But for charts, we usually want % of START stock.
        # Let's rely on standard logic: Cumulative deaths / Intake.
        # If Production, Cumulative deaths (since prod start) / Prod Start Stock.
        # This matches the behavior of daily charts.

        # We will assume Start Stock is global intake unless we detect phase shift logic?
        # metrics.py's enrich logic is best.
        # Let's just pick the last day of the week from daily_stats and take its cumulative %?
        # Yes! That's the most accurate representation of "End of Week Cumulative %".

        weekly_map = {ws['week']: ws for ws in weekly_stats}

        chart_data_weekly = {
            'dates': [],
            'mortality_cum_male': [], 'mortality_cum_female': [],
            'mortality_weekly_male': [], 'mortality_weekly_female': [],
            'culls_weekly_male': [], 'culls_weekly_female': [],
            'avg_bw_male': [], 'avg_bw_female': [],
            'egg_prod': [],
            'bw_male_std': [], 'bw_female_std': [],
            'unif_male': [], 'unif_female': [],
            'notes': []
        }
        for i in range(1, 9):
            chart_data_weekly[f'bw_M{i}'] = []
            chart_data_weekly[f'bw_F{i}'] = []

        # Group daily_stats by week to get end-of-week cum values
        daily_by_week = {}
        for d in daily_stats:
            if d['week'] not in daily_by_week: daily_by_week[d['week']] = []
            daily_by_week[d['week']].append(d)

        for w in sorted(weekly_map.keys()):
            ws = weekly_map[w]
            last_day = daily_by_week[w][-1]

            chart_data_weekly['dates'].append(f"Week {w}")
            chart_data_weekly['mortality_cum_male'].append(round(last_day['mortality_cum_male_pct'], 2))
            chart_data_weekly['mortality_cum_female'].append(round(last_day['mortality_cum_female_pct'], 2))

            chart_data_weekly['mortality_weekly_male'].append(round(ws['mortality_male_pct'], 2))
            chart_data_weekly['mortality_weekly_female'].append(round(ws['mortality_female_pct'], 2))
            chart_data_weekly['culls_weekly_male'].append(round(ws['culls_male_pct'], 2))
            chart_data_weekly['culls_weekly_female'].append(round(ws['culls_female_pct'], 2))

            chart_data_weekly['avg_bw_male'].append(round_to_whole(ws['body_weight_male']) if ws['body_weight_male'] > 0 else None)
            chart_data_weekly['avg_bw_female'].append(round_to_whole(ws['body_weight_female']) if ws['body_weight_female'] > 0 else None)

            chart_data_weekly['egg_prod'].append(round(ws['egg_prod_pct'], 2))
            chart_data_weekly['std_egg_prod'] = chart_data_weekly.get('std_egg_prod', [])
            chart_data_weekly['std_egg_prod'].append(round(ws['std_egg_prod'], 2))

            chart_data_weekly['hatch_egg_pct'] = chart_data_weekly.get('hatch_egg_pct', [])
            chart_data_weekly['hatch_egg_pct'].append(round(ws['hatch_egg_pct'], 2))

            chart_data_weekly['std_hatching_egg_pct'] = chart_data_weekly.get('std_hatching_egg_pct', [])
            chart_data_weekly['std_hatching_egg_pct'].append(round(ws['std_hatching_egg_pct'], 2))

            chart_data_weekly['cull_eggs_jumbo_pct'] = chart_data_weekly.get('cull_eggs_jumbo_pct', [])
            chart_data_weekly['cull_eggs_jumbo_pct'].append(round(ws['cull_eggs_jumbo_pct'], 2))

            chart_data_weekly['cull_eggs_small_pct'] = chart_data_weekly.get('cull_eggs_small_pct', [])
            chart_data_weekly['cull_eggs_small_pct'].append(round(ws['cull_eggs_small_pct'], 2))

            chart_data_weekly['cull_eggs_crack_pct'] = chart_data_weekly.get('cull_eggs_crack_pct', [])
            chart_data_weekly['cull_eggs_crack_pct'].append(round(ws['cull_eggs_crack_pct'], 2))

            chart_data_weekly['cull_eggs_abnormal_pct'] = chart_data_weekly.get('cull_eggs_abnormal_pct', [])
            chart_data_weekly['cull_eggs_abnormal_pct'].append(round(ws['cull_eggs_abnormal_pct'], 2))

            # Standard BW - Use Biological Age (w)
            std_bio = std_map.get(w)
            chart_data_weekly['bw_male_std'].append(std_bio.std_bw_male if std_bio and std_bio.std_bw_male > 0 else None)
            chart_data_weekly['bw_female_std'].append(std_bio.std_bw_female if std_bio and std_bio.std_bw_female > 0 else None)

            chart_data_weekly['unif_male'].append(scale_pct(ws['uniformity_male']) if ws['uniformity_male'] > 0 else None)
            chart_data_weekly['unif_female'].append(scale_pct(ws['uniformity_female']) if ws['uniformity_female'] > 0 else None)

            chart_data_weekly['water_per_bird'] = chart_data_weekly.get('water_per_bird', [])
            chart_data_weekly['water_per_bird'].append(round(ws['water_per_bird'], 1) if ws.get('water_per_bird', 0) >= 0 else None)
            chart_data_weekly['water_feed_ratio'] = chart_data_weekly.get('water_feed_ratio', [])
            chart_data_weekly['water_feed_ratio'].append(round(ws.get('water_feed_ratio'), 2) if ws.get('water_feed_ratio') is not None and ws.get('water_feed_ratio') >= 0 else None)

            chart_data_weekly['feed_male_gp_bird'] = chart_data_weekly.get('feed_male_gp_bird', [])
            chart_data_weekly['feed_male_gp_bird'].append(round(ws['feed_male_gp_bird'], 1))

            chart_data_weekly['feed_female_gp_bird'] = chart_data_weekly.get('feed_female_gp_bird', [])
            chart_data_weekly['feed_female_gp_bird'].append(round(ws['feed_female_gp_bird'], 1))

            # Aggregate Partitions for Weekly View
            def get_p_val(log, p_name, is_male, index):
                 p_map = {pw.partition_name: pw.body_weight for pw in log.partition_weights}
                 val = p_map.get(p_name, 0)
                 if val == 0:
                     attr = f'bw_male_p{index}' if is_male else f'bw_female_p{index}'
                     if hasattr(log, attr):
                         val = getattr(log, attr, 0)
                 return val

            for i in range(1, 9):
                m_key = f'M{i}'
                f_key = f'F{i}'
                m_vals = []
                f_vals = []

                for d in daily_by_week[w]:
                    log = d['log']
                    vm = get_p_val(log, m_key, True, i)
                    if vm and vm > 0: m_vals.append(vm)
                    vf = get_p_val(log, f_key, False, i)
                    if vf and vf > 0: f_vals.append(vf)

                val_m = round(sum(m_vals)/len(m_vals)) if m_vals else None
                val_f = round(sum(f_vals)/len(f_vals)) if f_vals else None

                chart_data_weekly[f'bw_M{i}'].append(val_m)
                chart_data_weekly[f'bw_F{i}'].append(val_f)

            # Aggregate Weekly Notes/Photos
            week_notes = []
            week_photos = []

            # From Daily Logs
            if w in daily_by_week:
                week_logs_data = daily_by_week[w]
                if week_logs_data:
                    w_start = week_logs_data[0]['date']
                    w_end = week_logs_data[-1]['date']

                    for d in week_logs_data:
                        log = d['log']
                        if log.clinical_notes:
                            week_notes.append(f"{log.date.strftime('%d/%m')}: {log.clinical_notes}")

                        for p in log.photos:
                            week_photos.append({
                                'url': url_for('uploaded_file', filename=os.path.basename(p.file_path)),
                                'name': f"{log.date.strftime('%d/%m')} {p.original_filename or 'Photo'}"
                            })

                    # Meds
                    w_meds = set()
                    for m in medications:
                        if m.start_date <= w_end and (m.end_date is None or m.end_date >= w_start):
                            w_meds.add(m.drug_name)
                    if w_meds: week_notes.append("Meds: " + ", ".join(w_meds))

                    # Vacs
                    w_vacs = set()
                    for v in vacs:
                        if v.actual_date and w_start <= v.actual_date <= w_end:
                            w_vacs.add(v.vaccine_name)
                    if w_vacs: week_notes.append("Vac: " + ", ".join(w_vacs))

            if week_notes or week_photos:
                chart_data_weekly['notes'].append({
                    'note': " | ".join(week_notes),
                    'photos': week_photos
                })
            else:
                chart_data_weekly['notes'].append(None)

        # Legacy keys for weekly
        chart_data_weekly['bw_male_p1'] = chart_data_weekly['bw_M1']
        chart_data_weekly['bw_male_p2'] = chart_data_weekly['bw_M2']
        chart_data_weekly['bw_female_p1'] = chart_data_weekly['bw_F1']
        chart_data_weekly['bw_female_p2'] = chart_data_weekly['bw_F2']
        chart_data_weekly['bw_female_p3'] = chart_data_weekly['bw_F3']
        chart_data_weekly['bw_female_p4'] = chart_data_weekly['bw_F4']

        # 5. Current Stats (Stock at end of last processed log)
        if daily_stats:
            last = daily_stats[-1]

            current_stats = {
                'male_prod': last.get('stock_male_prod_end', 0),
                'female_prod': last.get('stock_female_prod_end', 0),
                'male_hosp': last.get('stock_male_hosp_end', 0),
                'female_hosp': last.get('stock_female_hosp_end', 0),
                'male_ratio': last['male_ratio_stock'] if last.get('male_ratio_stock') else 0
            }
        else:
            current_stats = {
                'male_prod': flock.intake_male,
                'female_prod': flock.intake_female,
                'male_hosp': 0,
                'female_hosp': 0,
                'male_ratio': (flock.intake_male / flock.intake_female * 100) if flock.intake_female > 0 else 0
            }

        weekly_data.reverse()

        # Pre-check available reports for this flock
        from werkzeug.utils import secure_filename
        reports_dir = os.path.join(app.root_path, 'static', 'reports')
        available_reports = set()
        if os.path.exists(reports_dir):
            # We need a quick way to know which dates have reports
            prefix_to_match = f"_{secure_filename(flock.house.name)}_"
            for f in os.listdir(reports_dir):
                if prefix_to_match in f and f.endswith(".jpg"):
                    date_str = f.split("_")[0]
                    available_reports.add(date_str)

        breadcrumbs = [{'name': 'Dashboard', 'url': url_for('index')}, {'name': f'Flock {flock.flock_id}', 'url': None}]

        return render_template('flock_detail_modern.html', flock=flock, logs=list(reversed(enriched_logs)), weekly_data=weekly_data, chart_data=chart_data, chart_data_weekly=chart_data_weekly, current_stats=current_stats, global_std=gs, active_flocks=active_flocks, summary_dashboard=summary_dashboard, summary_table=summary_table, health_events=health_events, available_reports=available_reports, breadcrumbs=breadcrumbs)

    @app.route('/flock/<int:id>/toggle_phase', methods=['POST'])
    @login_required
    @dept_required('Farm')
    def toggle_phase(id):
        flock = Flock.query.get_or_404(id)
        if flock.phase == 'Rearing':
            flock.phase = 'Production'

            # production_start_date is now dynamic based on egg_prod_pct >= 5.0, so no direct assignment

            # Capture Start Counts
            prod_m = int(request.form.get('prod_start_male') or 0)
            prod_f = int(request.form.get('prod_start_female') or 0)
            hosp_m = int(request.form.get('prod_start_male_hosp') or 0)
            hosp_f = int(request.form.get('prod_start_female_hosp') or 0)

            flock.prod_start_male = prod_m
            flock.prod_start_female = prod_f
            flock.prod_start_male_hosp = hosp_m
            flock.prod_start_female_hosp = hosp_f

            # Calculate Loss Check (Expected vs Actual)
            stmt = db.session.query(
                db.func.sum(DailyLog.mortality_male),
                db.func.sum(DailyLog.mortality_female),
                db.func.sum(DailyLog.culls_male),
                db.func.sum(DailyLog.culls_female)
            ).filter(DailyLog.flock_id == id).first()

            rearing_loss_m = (stmt[0] or 0) + (stmt[2] or 0)
            rearing_loss_f = (stmt[1] or 0) + (stmt[3] or 0)

            expected_m = flock.intake_male - rearing_loss_m
            expected_f = flock.intake_female - rearing_loss_f

            actual_m = prod_m + hosp_m
            actual_f = prod_f + hosp_f

            diff_m = expected_m - actual_m
            diff_f = expected_f - actual_f

            msg = (
                f"Flock {flock.flock_id} switched to Production."
                f"{f' Warning: Count Discrepancy (M: {diff_m}, F: {diff_f}). Baseline reset to {actual_m} M / {actual_f} F.' if (diff_m != 0 or diff_f != 0) else ''}"
            )
            flash(msg, 'success' if (diff_m == 0 and diff_f == 0) else 'warning')
        else:
            flock.phase = 'Rearing'
            flash(f'Flock {flock.flock_id} switched back to Rearing phase.', 'warning')
        safe_commit()
        return redirect(url_for('index'))

    @app.route('/daily_log/photo/<int:photo_id>/delete', methods=['DELETE'])
    @login_required
    @dept_required('Farm')
    def delete_daily_log_photo(photo_id):
        photo = DailyLogPhoto.query.get_or_404(photo_id)
        # Check ownership/permissions if strict, but @dept_required('Farm') is enough for now.

        # Delete file from disk
        if photo.file_path and os.path.exists(photo.file_path):
            try:
                os.remove(photo.file_path)
            except OSError:
                pass # Ignore if file missing

        db.session.delete(photo)
        safe_commit()
        return '', 204

    @app.route('/daily_log/delete/<int:id>', methods=['POST'])
    @login_required
    @dept_required('Farm')
    def delete_daily_log(id):
        if not current_user.role == 'Admin': return redirect(url_for('index'))

        log = DailyLog.query.get_or_404(id)
        flock_id = log.flock_id
        date_str = log.date.strftime('%Y-%m-%d')

        log_user_activity(current_user.id, 'Delete', 'DailyLog', log.id, details={'date': date_str, 'flock_id': flock_id})

        # Cascade delete handles partitions, but maybe not Inventory Transactions (Usage)?
        # We should probably revert usage if tracked?
        # But usage is tracked via Medication start date or "Used in Daily Log" notes.
        # The 'daily_log' submission creates 'Medication' records.
        # We can try to find medications created on this date for this flock?
        # But medication might span multiple days.
        # Deleting a log is complex regarding side effects.
        # For now, just delete the log record itself (metrics).
        # Reverting inventory is too risky without explicit link.

        db.session.delete(log)
        safe_commit()
        flash("Daily Log deleted.", "info")
        return redirect(url_for('view_flock', id=flock_id))

    @app.route('/flock/<int:id>/close', methods=['POST'])
    @login_required
    @dept_required('Farm')
    def close_flock(id):
        flock = Flock.query.get_or_404(id)
        flock.status = 'Inactive'
        flock.end_date = date.today()
        safe_commit()
        flash(f'Flock {flock.flock_id} closed.', 'info')
        return redirect(url_for('index'))

    @app.route('/flocks', methods=['GET', 'POST'])
    @login_required
    @dept_required('Farm')
    def manage_flocks():
        if request.method == 'POST':
            house_name = request.form.get('house_name').strip()
            intake_date_str = request.form.get('intake_date')

            # production_start_date is now dynamic based on egg_prod_pct >= 5.0, so no direct assignment

            intake_male = int(request.form.get('intake_male') or 0)
            intake_female = int(request.form.get('intake_female') or 0)
            doa_male = int(request.form.get('doa_male') or 0)
            doa_female = int(request.form.get('doa_female') or 0)

            # Find or Create Farm
            farm_name = request.form.get('farm_name', '').strip()
            if not farm_name:
                flash('Error: Farm name is required.', 'danger')
                return redirect(url_for('manage_flocks'))

            farm_id = None
            farm = Farm.query.filter_by(name=farm_name).first()
            if not farm:
                farm = Farm(name=farm_name)
                db.session.add(farm)
                safe_commit()
                flash(f'Created new Farm: {farm_name}', 'info')
            farm_id = farm.id

            # Find or Create House
            house = House.query.filter_by(name=house_name).first()
            if not house:
                house = House(name=house_name)
                db.session.add(house)
                safe_commit()
                flash(f'Created new House: {house_name}', 'info')

            # Validation: Check if House has active flock
            existing_active = Flock.query.filter_by(house_id=house.id, status='Active').first()
            if existing_active:
                flash(f'Error: House {house.name} already has an active flock (Batch: {existing_active.flock_id})', 'danger')
                return redirect(url_for('manage_flocks'))

            # Generate Flock ID
            intake_date = datetime.strptime(intake_date_str, '%Y-%m-%d').date()
            date_str = intake_date.strftime('%y%m%d')

            # Calculate N (Total flocks for this house + 1)
            house_flock_count = Flock.query.filter_by(house_id=house.id).count()
            n = house_flock_count + 1

            flock_id = f"{house.name}_{date_str}_Batch{n}"

            new_flock = Flock(
                house_id=house.id,
                farm_id=farm_id,
                flock_id=flock_id,
                intake_date=intake_date,
                intake_male=intake_male,
                intake_female=intake_female,
                doa_male=doa_male,
                doa_female=doa_female
            )

            db.session.add(new_flock)
            db.session.flush()

            log_user_activity(current_user.id, 'Add', 'Flock', new_flock.flock_id, details={
                'house': house_name,
                'intake_male': intake_male,
                'intake_female': intake_female
            })

            safe_commit()

            initialize_sampling_schedule(new_flock.id)
            initialize_vaccine_schedule(new_flock.id)

            flash(f'Flock created successfully! Flock ID: {flock_id}', 'success')
            return redirect(url_for('index'))

        farms = Farm.query.all()
        houses = House.query.all()
        flocks = Flock.query.options(joinedload(Flock.house)).order_by(Flock.intake_date.desc()).all()

        # Bulk fetch cumulative mortality for all flocks to prevent N+1 queries
        # Using coalesce to handle NULL values correctly in SQL addition
        mortality_data = db.session.query(
            DailyLog.flock_id,
            db.func.sum(
                db.func.coalesce(DailyLog.mortality_male, 0) +
                db.func.coalesce(DailyLog.mortality_female, 0) +
                db.func.coalesce(DailyLog.culls_male, 0) +
                db.func.coalesce(DailyLog.culls_female, 0) +
                db.func.coalesce(DailyLog.mortality_male_hosp, 0) +
                db.func.coalesce(DailyLog.mortality_female_hosp, 0) +
                db.func.coalesce(DailyLog.culls_male_hosp, 0) +
                db.func.coalesce(DailyLog.culls_female_hosp, 0)
            )
        ).group_by(DailyLog.flock_id).all()

        mortality_map = {row[0]: row[1] for row in mortality_data}

        for flock in flocks:
            intake_m = flock.intake_male or 0
            intake_f = flock.intake_female or 0
            total_intake = intake_m + intake_f

            if total_intake > 0:
                cum_mort = mortality_map.get(flock.id, 0)
                flock.lifetime_cum_mort_pct = round((cum_mort / total_intake) * 100, 2)
            else:
                flock.lifetime_cum_mort_pct = 0.0

        return render_template('flock_form.html', farms=farms, houses=houses, flocks=flocks)

    @app.route('/flock_select')
    @login_required
    @dept_required('Farm')
    def flock_select():
        active_flocks = Flock.query.options(joinedload(Flock.house)).filter_by(status='Active').all()

        if active_flocks:
                active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else ''))

        if not active_flocks:
            flash("No active flocks found.", "warning")
            return redirect(url_for('index'))

        return render_template('flock_select.html', active_flocks=active_flocks)

    @app.route('/flock/<int:id>/delete', methods=['POST'])
    @login_required
    @dept_required('Farm')
    def delete_flock(id):
        flock = Flock.query.get_or_404(id)
        flock_id_str = flock.flock_id

        log_user_activity(current_user.id, 'Delete', 'Flock', flock_id_str)

        db.session.delete(flock)
        safe_commit()
        flash(f'Flock {flock_id_str} deleted.', 'warning')
        return redirect(url_for('manage_flocks'))

    @app.route('/flock/<int:id>/edit', methods=['GET', 'POST'])
    @login_required
    @dept_required('Farm')
    def edit_flock(id):
        flock = Flock.query.get_or_404(id)
        if request.method == 'POST':
            old_data = {
                'flock_id': flock.flock_id,
                'intake_date': flock.intake_date.strftime('%Y-%m-%d') if flock.intake_date else None,
                'intake_male': flock.intake_male,
                'intake_female': flock.intake_female
            }

            # Flock ID (ID) Update
            new_flock_id = request.form.get('flock_id').strip()
            if new_flock_id and new_flock_id != flock.flock_id:
                # Check for uniqueness
                existing = Flock.query.filter_by(flock_id=new_flock_id).first()
                if existing:
                    flash(f'Error: Flock ID "{new_flock_id}" already exists.', 'danger')
                    return render_template('flock_edit.html', flock=flock)
                flock.flock_id = new_flock_id

            intake_date_str = request.form.get('intake_date')
            if intake_date_str:
                flock.intake_date = datetime.strptime(intake_date_str, '%Y-%m-%d').date()

            # production_start_date is now dynamic based on egg_prod_pct >= 5.0, so no direct assignment

            lay_date_str = request.form.get('start_of_lay_date')
            if lay_date_str:
                 flock.start_of_lay_date = datetime.strptime(lay_date_str, '%Y-%m-%d').date()
            else:
                 flock.start_of_lay_date = None

            flock.intake_male = int(request.form.get('intake_male') or 0)
            flock.intake_female = int(request.form.get('intake_female') or 0)
            flock.doa_male = int(request.form.get('doa_male') or 0)
            flock.doa_female = int(request.form.get('doa_female') or 0)

            flock.prod_start_male = int(request.form.get('prod_start_male') or 0)
            flock.prod_start_female = int(request.form.get('prod_start_female') or 0)
            flock.prod_start_male_hosp = int(request.form.get('prod_start_male_hosp') or 0)
            flock.prod_start_female_hosp = int(request.form.get('prod_start_female_hosp') or 0)

            # Farm Update
            farm_name = request.form.get('farm_name', '').strip()
            if not farm_name:
                flash('Error: Farm name is required.', 'danger')
                return render_template('flock_edit.html', flock=flock)

            farm = Farm.query.filter_by(name=farm_name).first()
            if not farm:
                farm = Farm(name=farm_name)
                db.session.add(farm)
                safe_commit()
            flock.farm_id = farm.id

            new_data = {
                'flock_id': flock.flock_id,
                'intake_date': flock.intake_date.strftime('%Y-%m-%d') if flock.intake_date else None,
                'intake_male': flock.intake_male,
                'intake_female': flock.intake_female
            }

            changes = {k: {'old': old_data[k], 'new': new_data[k]} for k in old_data if old_data[k] != new_data[k]}
            if changes:
                log_user_activity(current_user.id, 'Edit', 'Flock', flock.flock_id, details=changes)

            safe_commit()
            flash(f'Flock {flock.flock_id} updated.', 'success')
            return redirect(url_for('index'))

        farms = Farm.query.all()
        return render_template('flock_edit.html', flock=flock, farms=farms)

    @app.route('/history')
    @login_required
    @dept_required('Farm')
    def history():
        inactive_flocks = Flock.query.options(joinedload(Flock.house)).filter_by(status='Inactive').order_by(Flock.intake_date.desc()).all()
        return render_template('flock_history.html', inactive_flocks=inactive_flocks)
