from datetime import datetime, date, timedelta
import math

METRICS_REGISTRY = {
    # --- Mortality ---
    'mortality_female': {'label': 'Mortality Female (Count)', 'unit': '', 'type': 'raw'},
    'mortality_male': {'label': 'Mortality Male (Count)', 'unit': '', 'type': 'raw'},
    'mortality_female_pct': {'label': 'Mortality Female (%)', 'unit': '%', 'type': 'derived'},
    'mortality_male_pct': {'label': 'Mortality Male (%)', 'unit': '%', 'type': 'derived'},
    'mortality_cum_female_pct': {'label': 'Cum. Mortality Female (%)', 'unit': '%', 'type': 'derived'},
    'mortality_cum_male_pct': {'label': 'Cum. Mortality Male (%)', 'unit': '%', 'type': 'derived'},

    # --- Culls ---
    'culls_female': {'label': 'Culls Female (Count)', 'unit': '', 'type': 'raw'},
    'culls_male': {'label': 'Culls Male (Count)', 'unit': '', 'type': 'raw'},
    'culls_female_pct': {'label': 'Culls Female (%)', 'unit': '%', 'type': 'derived'},
    'culls_male_pct': {'label': 'Culls Male (%)', 'unit': '%', 'type': 'derived'},

    # --- Feed ---
    'feed_female_gp_bird': {'label': 'Feed Female (g/bird)', 'unit': 'g', 'type': 'raw'},
    'feed_male_gp_bird': {'label': 'Feed Male (g/bird)', 'unit': 'g', 'type': 'raw'},
    'feed_total_kg': {'label': 'Total Feed (Kg)', 'unit': 'Kg', 'type': 'derived'},

    # --- Water ---
    'water_total': {'label': 'Water Total (L)', 'unit': 'L', 'type': 'raw', 'field': 'water_intake_calculated'},
    'water_per_bird': {'label': 'Water per Bird (ml)', 'unit': 'ml', 'type': 'derived'},

    # --- Production ---
    'eggs_collected': {'label': 'Total Eggs', 'unit': '', 'type': 'raw'},
    'egg_prod_pct': {'label': 'Egg Production (%)', 'unit': '%', 'type': 'derived'},
    'hatch_eggs': {'label': 'Hatching Eggs', 'unit': '', 'type': 'derived'},
    'hatch_egg_pct': {'label': 'Hatching Egg %', 'unit': '%', 'type': 'derived'},
    'egg_weight': {'label': 'Egg Weight (g)', 'unit': 'g', 'type': 'raw'},

    # --- Cull Eggs ---
    'cull_eggs_total': {'label': 'Total Cull Eggs', 'unit': '', 'type': 'derived'},
    'cull_eggs_pct': {'label': 'Total Cull Eggs (%)', 'unit': '%', 'type': 'derived'},
    'cull_eggs_jumbo': {'label': 'Cull Eggs (Jumbo)', 'unit': '', 'type': 'raw'},
    'cull_eggs_small': {'label': 'Cull Eggs (Small)', 'unit': '', 'type': 'raw'},
    'cull_eggs_crack': {'label': 'Cull Eggs (Crack)', 'unit': '', 'type': 'raw'},
    'cull_eggs_abnormal': {'label': 'Cull Eggs (Abnormal)', 'unit': '', 'type': 'raw'},

    'cull_eggs_jumbo_pct': {'label': 'Cull Eggs Jumbo (%)', 'unit': '%', 'type': 'derived'},
    'cull_eggs_small_pct': {'label': 'Cull Eggs Small (%)', 'unit': '%', 'type': 'derived'},
    'cull_eggs_crack_pct': {'label': 'Cull Eggs Crack (%)', 'unit': '%', 'type': 'derived'},
    'cull_eggs_abnormal_pct': {'label': 'Cull Eggs Abnormal (%)', 'unit': '%', 'type': 'derived'},

    # --- Body Weight ---
    'body_weight_female': {'label': 'Body Weight Female (g)', 'unit': 'g', 'type': 'raw'},
    'body_weight_male': {'label': 'Body Weight Male (g)', 'unit': 'g', 'type': 'raw'},
    'uniformity_female': {'label': 'Uniformity Female (%)', 'unit': '%', 'type': 'raw'},
    'uniformity_male': {'label': 'Uniformity Male (%)', 'unit': '%', 'type': 'raw'},

    # --- Hatchability ---
    'hatchability_pct': {'label': 'Hatchability (Hatch of Set) %', 'unit': '%', 'type': 'derived'},
    'fertile_egg_pct': {'label': 'Fertility % (Hatchable)', 'unit': '%', 'type': 'derived'},
    'clear_egg_pct': {'label': 'Clear Egg %', 'unit': '%', 'type': 'derived'},
    'rotten_egg_pct': {'label': 'Rotten Egg %', 'unit': '%', 'type': 'derived'},
    'egg_set': {'label': 'Egg Set', 'unit': '', 'type': 'raw'},
    'hatched_chicks': {'label': 'Hatched Chicks', 'unit': '', 'type': 'raw'},
    'male_ratio_pct': {'label': 'Male Ratio %', 'unit': '%', 'type': 'raw'},
}

def round_safe(val, digits=2):
    if val is None: return 0.0
    try:
        return round(float(val), digits)
    except (ValueError, TypeError):
        return 0.0

def safe_div(num, den, multiplier=100.0):
    if den and den > 0:
        return (num / den) * multiplier
    return 0.0

def enrich_flock_data(flock, logs, hatchability_data=None):
    """
    Core function to process a flock's logs and return a list of enriched daily data points.
    Handles Phase Switching, Stock Tracking, and Derived Metrics.
    """

    # 1. Setup Hatchability Map
    hatch_map = {}
    if hatchability_data:
        for h in hatchability_data:
            hatch_map[h.setting_date] = h

    # 2. Setup Stock Variables
    # Initial Baseline: Intake
    start_m = flock.intake_male or 0
    start_f = flock.intake_female or 0

    # Running Stock (Production + Hospital)
    curr_m_prod = start_m
    curr_m_hosp = 0
    curr_f_prod = start_f
    curr_f_hosp = 0

    in_prod = False

    # Cumulative Counters (Reset on Phase Switch)
    cum_mort_m = 0
    cum_mort_f = 0
    cum_cull_m = 0
    cum_cull_f = 0

    # Global Cumulative (For total flock life) could be tracked if needed,
    # but charts usually respect the "Phase Baseline".

    daily_stats = []

    # Ensure logs are sorted
    sorted_logs = sorted(logs, key=lambda x: x.date)

    for log in sorted_logs:
        # --- A. Phase Switch Logic ---
        # If we hit the production start date, we reset the baseline if prod_start counts are provided.
        if not in_prod and flock.production_start_date and log.date >= flock.production_start_date:
             # Check if we have explicit start counts for production
             if (flock.prod_start_male or 0) > 0 or (flock.prod_start_female or 0) > 0:
                 in_prod = True
                 curr_m_prod = flock.prod_start_male or 0
                 curr_f_prod = flock.prod_start_female or 0
                 curr_m_hosp = flock.prod_start_male_hosp or 0
                 curr_f_hosp = flock.prod_start_female_hosp or 0

                 # Reset Baseline for Cumulative Calcs
                 start_m = curr_m_prod + curr_m_hosp
                 start_f = curr_f_prod + curr_f_hosp

                 # Reset Cumulative Loss Counters
                 cum_mort_m = 0
                 cum_mort_f = 0
                 cum_cull_m = 0
                 cum_cull_f = 0

        # --- B. Snapshot Stock (Start of Day) ---
        # Used for today's mortality % calculation
        stock_m_start = curr_m_prod + curr_m_hosp
        stock_f_start = curr_f_prod + curr_f_hosp

        # --- C. Calculate Daily Metrics ---

        # Raw Values
        mort_m = (log.mortality_male or 0) + (log.mortality_male_hosp or 0)
        mort_f = (log.mortality_female or 0) + (log.mortality_female_hosp or 0)
        cull_m = (log.culls_male or 0) + (log.culls_male_hosp or 0)
        cull_f = (log.culls_female or 0) + (log.culls_female_hosp or 0)

        eggs = log.eggs_collected or 0

        # Feed Multiplier
        feed_mult = 1.0
        if log.feed_program == 'Skip-a-day': feed_mult = 2.0
        elif log.feed_program == '2/1': feed_mult = 1.5

        feed_m_kg = (log.feed_male_gp_bird * feed_mult * stock_m_start) / 1000.0 if stock_m_start > 0 else 0
        feed_f_kg = (log.feed_female_gp_bird * feed_mult * stock_f_start) / 1000.0 if stock_f_start > 0 else 0

        # Cull Eggs
        jumbo = log.cull_eggs_jumbo or 0
        small = log.cull_eggs_small or 0
        crack = log.cull_eggs_crack or 0
        abnormal = log.cull_eggs_abnormal or 0
        total_cull_eggs = jumbo + small + crack + abnormal
        hatch_eggs = eggs - total_cull_eggs

        # Cumulatives (Add today's loss)
        cum_mort_m += mort_m
        cum_mort_f += mort_f
        cum_cull_m += cull_m
        cum_cull_f += cull_f

        # Metrics Dict
        d = {
            'date': log.date,
            'log': log, # Reference to original object
            'week': (log.date - flock.intake_date).days // 7 + 1,
            'age_days': (log.date - flock.intake_date).days,

            # Stocks
            'stock_male_start': stock_m_start,
            'stock_female_start': stock_f_start,
            'stock_male_prod_start': curr_m_prod,
            'stock_male_hosp_start': curr_m_hosp,
            'stock_female_prod_start': curr_f_prod,
            'stock_female_hosp_start': curr_f_hosp,
            'phase_start_male': start_m,
            'phase_start_female': start_f,
            'male_ratio_stock': safe_div(curr_m_prod, curr_f_prod),

            # Raw
            'mortality_male': mort_m,
            'mortality_female': mort_f,
            'culls_male': cull_m,
            'culls_female': cull_f,
            'eggs_collected': eggs,
            'hatch_eggs': hatch_eggs,
            'egg_weight': log.egg_weight,
            'feed_male_gp_bird': log.feed_male_gp_bird,
            'feed_female_gp_bird': log.feed_female_gp_bird,
            'feed_total_kg': feed_m_kg + feed_f_kg,
            'feed_m_kg': feed_m_kg,
            'feed_f_kg': feed_f_kg,
            'water_total': log.water_intake_calculated,

            # Cull Eggs
            'cull_eggs_jumbo': jumbo,
            'cull_eggs_small': small,
            'cull_eggs_crack': crack,
            'cull_eggs_abnormal': abnormal,
            'cull_eggs_total': total_cull_eggs,

            # BW (Use 0 if None/0 to keep data consistent, or None for charts?)
            # For data processing, 0 is safer for math, None better for charts.
            # We store raw values here.
            'body_weight_male': log.body_weight_male,
            'body_weight_female': log.body_weight_female,
            'uniformity_male': log.uniformity_male,
            'uniformity_female': log.uniformity_female,

            # Derived %
            'mortality_male_pct': safe_div(mort_m, stock_m_start),
            'mortality_female_pct': safe_div(mort_f, stock_f_start),
            'culls_male_pct': safe_div(cull_m, stock_m_start),
            'culls_female_pct': safe_div(cull_f, stock_f_start),

            'mortality_cum_male': cum_mort_m,
            'mortality_cum_female': cum_mort_f,
            'mortality_cum_male_pct': safe_div(cum_mort_m, start_m),
            'mortality_cum_female_pct': safe_div(cum_mort_f, start_f),

            'egg_prod_pct': safe_div(eggs, stock_f_start),
            'hatch_egg_pct': safe_div(hatch_eggs, eggs),

            'cull_eggs_pct': safe_div(total_cull_eggs, eggs),
            'cull_eggs_jumbo_pct': safe_div(jumbo, eggs),
            'cull_eggs_small_pct': safe_div(small, eggs),
            'cull_eggs_crack_pct': safe_div(crack, eggs),
            'cull_eggs_abnormal_pct': safe_div(abnormal, eggs),

            'water_per_bird': safe_div(log.water_intake_calculated * 1000, (stock_m_start + stock_f_start), multiplier=1.0)
        }

        # Hatchability Merge
        if log.date in hatch_map:
            h = hatch_map[log.date]
            d.update({
                'hatchability_pct': h.hatchability_pct,
                'fertile_egg_pct': h.fertile_egg_pct,
                'clear_egg_pct': h.clear_egg_pct,
                'rotten_egg_pct': h.rotten_egg_pct,
                'egg_set': h.egg_set,
                'hatched_chicks': h.hatched_chicks,
                'male_ratio_pct': h.male_ratio_pct
            })
        else:
            d.update({
                'hatchability_pct': None, 'fertile_egg_pct': None,
                'clear_egg_pct': None, 'rotten_egg_pct': None,
                'egg_set': None, 'hatched_chicks': None,
                'male_ratio_pct': None
            })

        # --- D. Update End-of-Day Stocks ---
        # Apply Mortality & Culls
        curr_m_prod -= (log.mortality_male or 0) + (log.culls_male or 0)
        curr_f_prod -= (log.mortality_female or 0) + (log.culls_female or 0)
        curr_m_hosp -= (log.mortality_male_hosp or 0) + (log.culls_male_hosp or 0)
        curr_f_hosp -= (log.mortality_female_hosp or 0) + (log.culls_female_hosp or 0)

        # Apply Transfers
        curr_m_prod += (log.males_moved_to_prod or 0) - (log.males_moved_to_hosp or 0)
        curr_m_hosp += (log.males_moved_to_hosp or 0) - (log.males_moved_to_prod or 0)

        curr_f_prod += (log.females_moved_to_prod or 0) - (log.females_moved_to_hosp or 0)
        curr_f_hosp += (log.females_moved_to_hosp or 0) - (log.females_moved_to_prod or 0)

        # Safety clamp
        if curr_m_prod < 0: curr_m_prod = 0
        if curr_f_prod < 0: curr_f_prod = 0
        if curr_m_hosp < 0: curr_m_hosp = 0
        if curr_f_hosp < 0: curr_f_hosp = 0

        d.update({
            'stock_male_prod_end': curr_m_prod,
            'stock_female_prod_end': curr_f_prod,
            'stock_male_hosp_end': curr_m_hosp,
            'stock_female_hosp_end': curr_f_hosp
        })

        daily_stats.append(d)

    return daily_stats

def aggregate_weekly_metrics(daily_stats):
    """
    Aggregates daily stats into weekly summaries.
    """
    weekly_stats = {}

    for d in daily_stats:
        w = d['week']
        if w not in weekly_stats:
            weekly_stats[w] = {
                'week': w,
                'count': 0,
                'stock_male_start': d['stock_male_start'], # Take start of week
                'stock_female_start': d['stock_female_start'],

                # Sums
                'mortality_male': 0, 'mortality_female': 0,
                'culls_male': 0, 'culls_female': 0,
                'eggs_collected': 0, 'hatch_eggs': 0,
                'feed_total_kg': 0,
                'feed_sum_m_kg': 0, 'feed_sum_f_kg': 0,
                'water_total_vol': 0,
                'stock_sum_male': 0, 'stock_sum_female': 0, # For weighted avgs

                # Averages (Sum then divide)
                'bw_male_sum': 0, 'bw_male_count': 0,
                'bw_female_sum': 0, 'bw_female_count': 0,
                'unif_male_sum': 0, 'unif_male_count': 0,
                'unif_female_sum': 0, 'unif_female_count': 0,

                # Hatchery (Sum)
                'egg_set': 0, 'hatched_chicks': 0,

                # Notes
                'notes': [],
                'photos': []
            }

        ws = weekly_stats[w]
        ws['count'] += 1
        ws['mortality_male'] += d['mortality_male']
        ws['mortality_female'] += d['mortality_female']
        ws['culls_male'] += d['culls_male']
        ws['culls_female'] += d['culls_female']
        ws['eggs_collected'] += d['eggs_collected']
        ws['hatch_eggs'] += d['hatch_eggs']
        ws['feed_total_kg'] += d['feed_total_kg']
        ws['feed_sum_m_kg'] += d['feed_m_kg']
        ws['feed_sum_f_kg'] += d['feed_f_kg']
        ws['water_total_vol'] += (d['water_total'] or 0)
        ws['stock_sum_male'] += d['stock_male_start']
        ws['stock_sum_female'] += d['stock_female_start']

        if d['body_weight_male'] and d['body_weight_male'] > 0:
            ws['bw_male_sum'] += d['body_weight_male']
            ws['bw_male_count'] += 1

        if d['body_weight_female'] and d['body_weight_female'] > 0:
            ws['bw_female_sum'] += d['body_weight_female']
            ws['bw_female_count'] += 1

        if d['uniformity_male'] and d['uniformity_male'] > 0:
            ws['unif_male_sum'] += d['uniformity_male']
            ws['unif_male_count'] += 1

        if d['uniformity_female'] and d['uniformity_female'] > 0:
            ws['unif_female_sum'] += d['uniformity_female']
            ws['unif_female_count'] += 1

        if d['egg_set']: ws['egg_set'] += d['egg_set']
        if d['hatched_chicks']: ws['hatched_chicks'] += d['hatched_chicks']

        if d['log'].clinical_notes:
            ws['notes'].append(d['log'].clinical_notes)
        if d['log'].photo_path:
            ws['photos'].append(d['log'].photo_path)

    # Finalize Averages
    result = []
    for w in sorted(weekly_stats.keys()):
        ws = weekly_stats[w]

        # Calculate Derived Weekly Metrics
        ws['mortality_male_pct'] = safe_div(ws['mortality_male'], ws['stock_male_start'])
        ws['mortality_female_pct'] = safe_div(ws['mortality_female'], ws['stock_female_start'])
        ws['culls_male_pct'] = safe_div(ws['culls_male'], ws['stock_male_start'])
        ws['culls_female_pct'] = safe_div(ws['culls_female'], ws['stock_female_start'])

        # Hen Days for Egg Prod % (Average Stock * Days) OR Sum of daily stocks?
        # Typically Egg Prod % = Total Eggs / (Avg Hen Stock * 7)
        # Avg Hen Stock = Start - (Mort/2).
        avg_hen = ws['stock_female_start'] - ((ws['mortality_female'] + ws['culls_female']) / 2)
        ws['egg_prod_pct'] = safe_div(ws['eggs_collected'], avg_hen * ws['count'])

        ws['hatch_egg_pct'] = safe_div(ws['hatch_eggs'], ws['eggs_collected'])
        ws['hatchability_pct'] = safe_div(ws['hatched_chicks'], ws['egg_set'])

        ws['body_weight_male'] = ws['bw_male_sum'] / ws['bw_male_count'] if ws['bw_male_count'] > 0 else 0
        ws['body_weight_female'] = ws['bw_female_sum'] / ws['bw_female_count'] if ws['bw_female_count'] > 0 else 0

        ws['uniformity_male'] = ws['unif_male_sum'] / ws['unif_male_count'] if ws['unif_male_count'] > 0 else 0
        ws['uniformity_female'] = ws['unif_female_sum'] / ws['unif_female_count'] if ws['unif_female_count'] > 0 else 0

        # Feed/Water per bird (Weighted Avg)
        # Note: Feed Kg includes both M+F? No, usually separate lines.
        # But here 'feed_total_kg' is combined.
        # However, for charts we usually want 'g/bird'.
        # Since we lost the split Kg in aggregation (my bad), I can't reconstruct M vs F feed g/bird accurately without tracking Sum(FeedM_Kg) and Sum(FeedF_Kg).
        # I'll calculate Water per bird.
        ws['water_per_bird'] = safe_div(ws['water_total_vol'] * 1000, ws['stock_sum_male'] + ws['stock_sum_female'], multiplier=1.0)

        ws['feed_male_gp_bird'] = safe_div(ws['feed_sum_m_kg'] * 1000, ws['stock_sum_male'], multiplier=1.0)
        ws['feed_female_gp_bird'] = safe_div(ws['feed_sum_f_kg'] * 1000, ws['stock_sum_female'], multiplier=1.0)

        result.append(ws)

    return result

def aggregate_monthly_metrics(daily_stats):
    """
    Aggregates daily stats into monthly summaries.
    """
    monthly_stats = {}

    for d in daily_stats:
        # Group by YYYY-MM
        m_key = d['date'].strftime('%Y-%m')

        if m_key not in monthly_stats:
            monthly_stats[m_key] = {
                'month': m_key,
                'count': 0,
                'stock_male_start': d['stock_male_start'], # Take start of month
                'stock_female_start': d['stock_female_start'],
                'date_start': d['date'],
                'date_end': d['date'],

                # Sums
                'mortality_male': 0, 'mortality_female': 0,
                'culls_male': 0, 'culls_female': 0,
                'eggs_collected': 0, 'hatch_eggs': 0,
                'feed_total_kg': 0,
                'feed_sum_m_kg': 0, 'feed_sum_f_kg': 0,
                'water_total_vol': 0,
                'stock_sum_male': 0, 'stock_sum_female': 0,

                # Averages (Sum then divide)
                'bw_male_sum': 0, 'bw_male_count': 0,
                'bw_female_sum': 0, 'bw_female_count': 0,
                'unif_male_sum': 0, 'unif_male_count': 0,
                'unif_female_sum': 0, 'unif_female_count': 0,

                # Hatchery (Sum)
                'egg_set': 0, 'hatched_chicks': 0,

                'notes': [],
                'photos': []
            }

        ms = monthly_stats[m_key]
        ms['count'] += 1
        ms['date_end'] = d['date']
        ms['mortality_male'] += d['mortality_male']
        ms['mortality_female'] += d['mortality_female']
        ms['culls_male'] += d['culls_male']
        ms['culls_female'] += d['culls_female']
        ms['eggs_collected'] += d['eggs_collected']
        ms['hatch_eggs'] += d['hatch_eggs']
        ms['feed_total_kg'] += d['feed_total_kg']
        ms['feed_sum_m_kg'] += d['feed_m_kg']
        ms['feed_sum_f_kg'] += d['feed_f_kg']
        ms['water_total_vol'] += (d['water_total'] or 0)
        ms['stock_sum_male'] += d['stock_male_start']
        ms['stock_sum_female'] += d['stock_female_start']

        if d['body_weight_male'] and d['body_weight_male'] > 0:
            ms['bw_male_sum'] += d['body_weight_male']
            ms['bw_male_count'] += 1

        if d['body_weight_female'] and d['body_weight_female'] > 0:
            ms['bw_female_sum'] += d['body_weight_female']
            ms['bw_female_count'] += 1

        if d['uniformity_male'] and d['uniformity_male'] > 0:
            ms['unif_male_sum'] += d['uniformity_male']
            ms['unif_male_count'] += 1

        if d['uniformity_female'] and d['uniformity_female'] > 0:
            ms['unif_female_sum'] += d['uniformity_female']
            ms['unif_female_count'] += 1

        if d['egg_set']: ms['egg_set'] += d['egg_set']
        if d['hatched_chicks']: ms['hatched_chicks'] += d['hatched_chicks']

        if d['log'].clinical_notes:
            ms['notes'].append(d['log'].clinical_notes)
        if d['log'].photo_path:
            ms['photos'].append(d['log'].photo_path)

    # Finalize Averages
    result = []
    for k in sorted(monthly_stats.keys()):
        ms = monthly_stats[k]

        # Calculate Derived
        ms['mortality_male_pct'] = safe_div(ms['mortality_male'], ms['stock_male_start'])
        ms['mortality_female_pct'] = safe_div(ms['mortality_female'], ms['stock_female_start'])
        ms['culls_male_pct'] = safe_div(ms['culls_male'], ms['stock_male_start'])
        ms['culls_female_pct'] = safe_div(ms['culls_female'], ms['stock_female_start'])

        avg_hen = ms['stock_female_start'] - ((ms['mortality_female'] + ms['culls_female']) / 2)
        ms['egg_prod_pct'] = safe_div(ms['eggs_collected'], avg_hen * ms['count'])

        ms['hatch_egg_pct'] = safe_div(ms['hatch_eggs'], ms['eggs_collected'])
        ms['hatchability_pct'] = safe_div(ms['hatched_chicks'], ms['egg_set'])

        ms['body_weight_male'] = ms['bw_male_sum'] / ms['bw_male_count'] if ms['bw_male_count'] > 0 else 0
        ms['body_weight_female'] = ms['bw_female_sum'] / ms['bw_female_count'] if ms['bw_female_count'] > 0 else 0

        ms['uniformity_male'] = ms['unif_male_sum'] / ms['unif_male_count'] if ms['unif_male_count'] > 0 else 0
        ms['uniformity_female'] = ms['unif_female_sum'] / ms['unif_female_count'] if ms['unif_female_count'] > 0 else 0

        ms['water_per_bird'] = safe_div(ms['water_total_vol'] * 1000, ms['stock_sum_male'] + ms['stock_sum_female'], multiplier=1.0)
        ms['feed_male_gp_bird'] = safe_div(ms['feed_sum_m_kg'] * 1000, ms['stock_sum_male'], multiplier=1.0)
        ms['feed_female_gp_bird'] = safe_div(ms['feed_sum_f_kg'] * 1000, ms['stock_sum_female'], multiplier=1.0)

        result.append(ms)

    return result

def calculate_metrics(logs, flock, requested_metrics, hatchability_data=None, start_date=None, end_date=None):
    """
    Adapter function to maintain compatibility with existing API but use new engine.
    """
    daily_stats = enrich_flock_data(flock, logs, hatchability_data)

    data = {m: [] for m in requested_metrics if m not in ('dates', 'weeks')}
    if 'dates' in requested_metrics: data['dates'] = []
    if 'weeks' in requested_metrics: data['weeks'] = []

    for d in daily_stats:
        if start_date and d['date'] < start_date: continue
        if end_date and d['date'] > end_date: continue

        if 'dates' in requested_metrics:
            data['dates'].append(d['date'].isoformat())
        if 'weeks' in requested_metrics:
            data['weeks'].append(d['week'])

        for m in data:
            if m in ('dates', 'weeks'): continue
            val = d.get(m)
            # Handle list of None vs 0 based on type?
            # Existing API expects None for missing charts data sometimes.
            if val is not None:
                data[m].append(val)
            else:
                data[m].append(None)

    return data
