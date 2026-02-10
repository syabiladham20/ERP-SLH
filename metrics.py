from flask import url_for
import os

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

    # --- Water ---
    'water_total': {'label': 'Water Total (L)', 'unit': 'L', 'type': 'raw', 'field': 'water_intake_calculated'},
    'water_per_bird': {'label': 'Water per Bird (ml)', 'unit': 'ml', 'type': 'derived'},

    # --- Production ---
    'eggs_collected': {'label': 'Total Eggs', 'unit': '', 'type': 'raw'},
    'egg_prod_pct': {'label': 'Egg Production (%)', 'unit': '%', 'type': 'derived'},
    'hatch_eggs': {'label': 'Hatching Eggs', 'unit': '', 'type': 'derived'},
    'hatch_pct': {'label': 'Hatchability (%)', 'unit': '%', 'type': 'derived'},
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
    'hatchability_pct': {'label': 'Hatchability (Hatch of Total) %', 'unit': '%', 'type': 'derived'},
    'fertile_egg_pct': {'label': 'Fertile Egg % (Hatchable)', 'unit': '%', 'type': 'derived'},
    'clear_egg_pct': {'label': 'Clear Egg %', 'unit': '%', 'type': 'derived'},
    'rotten_egg_pct': {'label': 'Rotten Egg %', 'unit': '%', 'type': 'derived'},
    'egg_set': {'label': 'Egg Set', 'unit': '', 'type': 'raw'},
    'hatched_chicks': {'label': 'Hatched Chicks', 'unit': '', 'type': 'raw'},
    'male_ratio_pct': {'label': 'Male Ratio %', 'unit': '%', 'type': 'raw'},
}

def calculate_metrics(logs, flock, requested_metrics, hatchability_data=None):
    """
    Process logs and return a dictionary of lists for requested metrics.
    Also returns 'dates' and 'weeks'.
    """
    data = {m: [] for m in requested_metrics}

    # Index Hatchability by Setting Date
    hatch_map = {}
    if hatchability_data:
        for h in hatchability_data:
            hatch_map[h.setting_date] = h

    data['dates'] = []
    data['weeks'] = []

    # Init Cumulatives
    cum_mort_m = 0
    cum_mort_f = 0
    cum_cull_m = 0
    cum_cull_f = 0

    start_m = flock.intake_male or 1
    start_f = flock.intake_female or 1

    for log in logs:
        data['dates'].append(log.date.isoformat())
        days_diff = (log.date - flock.intake_date).days
        week = (days_diff // 7) + 1
        data['weeks'].append(week)

        # Update Stocks
        # Note: log.mortality is for THIS day. Stock is Start - Cum(Prev).
        # But for rate calculation, usually we use "Current Stock" (Start - Cum(Including Today? or Yesterday?))
        # Standard industry practice: % of Current Stock.

        curr_stock_m = start_m - cum_mort_m - cum_cull_m
        curr_stock_f = start_f - cum_mort_f - cum_cull_f

        # Prevent div/0
        if curr_stock_m <= 0: curr_stock_m = 1
        if curr_stock_f <= 0: curr_stock_f = 1

        # Calculate derived values for this day
        row_vals = {}

        # Basic Raw Helpers
        def get_raw(field):
            return getattr(log, field, 0)

        row_vals['mortality_female'] = log.mortality_female
        row_vals['mortality_male'] = log.mortality_male
        row_vals['culls_female'] = log.culls_female
        row_vals['culls_male'] = log.culls_male
        row_vals['eggs_collected'] = log.eggs_collected
        row_vals['feed_female_gp_bird'] = log.feed_female_gp_bird
        row_vals['feed_male_gp_bird'] = log.feed_male_gp_bird

        # BW/Uniformity: Return None if 0 to avoid chart drops
        row_vals['body_weight_female'] = log.body_weight_female if log.body_weight_female > 0 else None
        row_vals['body_weight_male'] = log.body_weight_male if log.body_weight_male > 0 else None
        row_vals['uniformity_female'] = log.uniformity_female if log.uniformity_female > 0 else None
        row_vals['uniformity_male'] = log.uniformity_male if log.uniformity_male > 0 else None

        row_vals['egg_weight'] = log.egg_weight
        row_vals['water_total'] = log.water_intake_calculated
        row_vals['cull_eggs_jumbo'] = log.cull_eggs_jumbo
        row_vals['cull_eggs_small'] = log.cull_eggs_small
        row_vals['cull_eggs_abnormal'] = log.cull_eggs_abnormal
        row_vals['cull_eggs_crack'] = log.cull_eggs_crack

        # Derived
        row_vals['mortality_female_pct'] = (log.mortality_female / curr_stock_f) * 100
        row_vals['mortality_male_pct'] = (log.mortality_male / curr_stock_m) * 100
        row_vals['culls_female_pct'] = (log.culls_female / curr_stock_f) * 100
        row_vals['culls_male_pct'] = (log.culls_male / curr_stock_m) * 100

        # Update Cumulative for NEXT loop, but we need current cum for this row?
        # Cumulative Mortality usually includes today.
        cum_mort_m += log.mortality_male
        cum_mort_f += log.mortality_female
        cum_cull_m += log.culls_male
        cum_cull_f += log.culls_female

        row_vals['mortality_cum_female_pct'] = (cum_mort_f / start_f) * 100
        row_vals['mortality_cum_male_pct'] = (cum_mort_m / start_m) * 100

        row_vals['egg_prod_pct'] = (log.eggs_collected / curr_stock_f) * 100

        total_cull_eggs = (log.cull_eggs_jumbo + log.cull_eggs_small +
                           log.cull_eggs_abnormal + log.cull_eggs_crack)
        row_vals['cull_eggs_total'] = total_cull_eggs
        row_vals['cull_eggs_pct'] = (total_cull_eggs / log.eggs_collected * 100) if log.eggs_collected > 0 else 0

        row_vals['cull_eggs_jumbo_pct'] = (log.cull_eggs_jumbo / log.eggs_collected * 100) if log.eggs_collected > 0 else 0
        row_vals['cull_eggs_small_pct'] = (log.cull_eggs_small / log.eggs_collected * 100) if log.eggs_collected > 0 else 0
        row_vals['cull_eggs_crack_pct'] = (log.cull_eggs_crack / log.eggs_collected * 100) if log.eggs_collected > 0 else 0
        row_vals['cull_eggs_abnormal_pct'] = (log.cull_eggs_abnormal / log.eggs_collected * 100) if log.eggs_collected > 0 else 0

        row_vals['hatch_eggs'] = log.eggs_collected - total_cull_eggs
        row_vals['hatch_pct'] = (row_vals['hatch_eggs'] / log.eggs_collected * 100) if log.eggs_collected > 0 else 0

        stock_total = curr_stock_m + curr_stock_f
        row_vals['water_per_bird'] = (log.water_intake_calculated * 1000) / stock_total if stock_total > 0 else 0

        # Hatchability Mapping
        if log.date in hatch_map:
            h = hatch_map[log.date]
            row_vals['hatchability_pct'] = h.hatchability_pct
            row_vals['fertile_egg_pct'] = h.fertile_egg_pct
            row_vals['clear_egg_pct'] = h.clear_egg_pct
            row_vals['rotten_egg_pct'] = h.rotten_egg_pct
            row_vals['egg_set'] = h.egg_set
            row_vals['hatched_chicks'] = h.hatched_chicks
            row_vals['male_ratio_pct'] = h.male_ratio_pct
        else:
             # Explicitly set to None for missing days to allow spanGaps or gaps
            row_vals['hatchability_pct'] = None
            row_vals['fertile_egg_pct'] = None
            row_vals['clear_egg_pct'] = None
            row_vals['rotten_egg_pct'] = None
            row_vals['egg_set'] = None
            row_vals['hatched_chicks'] = None
            row_vals['male_ratio_pct'] = None

        # Fill Data
        for m in requested_metrics:
            val = row_vals.get(m, 0)
            # Rounding
            if isinstance(val, float):
                val = round(val, 2)
            data[m].append(val)

    return data
