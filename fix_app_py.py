import re

with open('app.py', 'r') as f:
    content = f.read()

content = re.sub(
    r'<<<<<<< HEAD\n\s*if delta < 0:\n\s*return jsonify\(\{.*?\}\), 400\n\n\s*weeks = delta // 7\n=======\n\s*if delta <= 0:\n\s*return jsonify\(\{.*?\}\), 400\n\n\s*weeks = \(\(delta - 1\) // 7\) \+ 1\n>>>>>>> main\n',
    '''    if delta < 0:
        return jsonify({'error': 'Date is before intake date'}), 400

    weeks = delta // 7\n''',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'<<<<<<< HEAD\n\s*"""Returns total days since intake \(Day 1 is the day after intake\)\."""\n=======\n\s*"""Returns the total days since intake \(Day 1 is the day after intake\)\."""\n>>>>>>> main\n',
    '        """Returns total days since intake (Day 1 is the day after intake)."""\n',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'<<<<<<< HEAD\n\s*"""Returns the standard poultry string format with date \(e\.g\., \'2\.1 \(13-05\)\'\)\."""\n\s*days = self\.age_days_total\n\s*if days <= 0:\n\s*return "0\.0"\n\n=======\n\s*"""Returns the standard poultry string format \(e\.g\., \'2\.1\' for Week 2, Day 1\)\."""\n\s*days = self\.age_days_total\n\s*if days <= 0:\n\s*return "0\.0"\n>>>>>>> main\n',
    '''        """Returns the standard poultry string format with date (e.g., '2.1 (13-05)')."""
        days = self.age_days_total
        if days <= 0:
            return "0.0"\n\n''',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'<<<<<<< HEAD\n\s*# We will build dataset groups for each chart: generalChart, hatchingEggChart, waterChart, feedChart, maleChart, femaleChart\n\s*# Each group will have its own \'labels\' and \'datasets\'\n\n\s*charts = \{\n\s*\'generalChart\': \{\'labels\': \[\], \'datasets\': \[\]\},\n=======\n\s*charts = \{\n\s*\'generalChart\': \{\'labels\': \[\], \'datasets\': \[\]\},\n>>>>>>> main\n',
    '''    # We will build dataset groups for each chart: generalChart, hatchingEggChart, waterChart, feedChart, maleChart, femaleChart
    # Each group will have its own 'labels' and 'datasets'

    charts = {
        'generalChart': {'labels': [], 'datasets': []},\n''',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'<<<<<<< HEAD\n\s*if datalabels: ds\["datalabels"\] = datalabels\n=======\n>>>>>>> main\n',
    '        if datalabels: ds["datalabels"] = datalabels\n',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'<<<<<<< HEAD\n\s*ds_std_egg_prod = init_dataset\("Std Egg Prod %", "#888888", "y", "line", False, borderDash=\[5,5\], hidden=True, datalabels=\{"display": False\}\)\n\s*ds_mort_f = init_dataset\("Fem Depletion %", "#d63939", "y1", "bar", True, is_bar=True\)\n\s*ds_mort_m = init_dataset\("Male Depletion %", "#f59f00", "y1", "bar", True, is_bar=True\)\n\s*ds_std_mort_f = init_dataset\("Std Fem Depletion %", "#888888", "y1", "line", False, borderDash=\[5,5\], hidden=True, datalabels=\{"display": False\}\)\n=======\n\s*ds_std_egg_prod = init_dataset\("Std Egg Prod %", "#206bc4", "y", "line", False, borderDash=\[5,5\], hidden=True\)\n\s*ds_mort_f = init_dataset\("Fem Depletion %", "#d63939", "y1", "bar", True, is_bar=True\)\n\s*ds_mort_m = init_dataset\("Male Depletion %", "#f59f00", "y1", "bar", True, is_bar=True\)\n\s*ds_std_mort_f = init_dataset\("Std Fem Depletion %", "#d63939", "y1", "line", False, borderDash=\[5,5\], hidden=True\)\n>>>>>>> main\n',
    '''    ds_std_egg_prod = init_dataset("Std Egg Prod %", "#888888", "y", "line", False, borderDash=[5,5], hidden=True, datalabels={"display": False})
    ds_mort_f = init_dataset("Fem Depletion %", "#d63939", "y1", "bar", True, is_bar=True)
    ds_mort_m = init_dataset("Male Depletion %", "#f59f00", "y1", "bar", True, is_bar=True)
    ds_std_mort_f = init_dataset("Std Fem Depletion %", "#888888", "y1", "line", False, borderDash=[5,5], hidden=True, datalabels={"display": False})\n''',
    content,
    flags=re.DOTALL
)


content = re.sub(
    r'<<<<<<< HEAD\n\s*ds_bw_f_std = init_dataset\("Std Female BW \(g\)", "#888888", "y", "line", False, borderDash=\[5,5\], datalabels=\{"display": False\}\)\n=======\n\s*ds_bw_f_std = init_dataset\("Std Female BW \(g\)", "#d63939", "y", "line", False, borderDash=\[5,5\]\)\n>>>>>>> main\n',
    '    ds_bw_f_std = init_dataset("Std Female BW (g)", "#888888", "y", "line", False, borderDash=[5,5], datalabels={"display": False})\n',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'<<<<<<< HEAD\n\s*ds_bw_m_std = init_dataset\("Std Male BW \(g\)", "#888888", "y", "line", False, borderDash=\[5,5\], datalabels=\{"display": False\}\)\n=======\n\s*ds_bw_m_std = init_dataset\("Std Male BW \(g\)", "#f59f00", "y", "line", False, borderDash=\[5,5\]\)\n>>>>>>> main\n',
    '    ds_bw_m_std = init_dataset("Std Male BW (g)", "#888888", "y", "line", False, borderDash=[5,5], datalabels={"display": False})\n',
    content,
    flags=re.DOTALL
)


content = re.sub(
    r'<<<<<<< HEAD\n\s*# Use new SSOT property\n\s*label = log\.age_week_format\n=======\n\s*# Calculate week and day\n\s*intake_date = flock\.intake_date\n\s*days = \(log\.date - intake_date\)\.days\n\n\s*if days <= 0:\n\s*label = "0\.0"\n\s*else:\n\s*w = \(\(days - 1\) // 7\) \+ 1\n\s*d_day = \(\(days - 1\) % 7\) \+ 1\n\s*label = f"\{w\}\.\{d_day\} \(\{log\.date\.strftime\(\'%d-%m\'\)\}\)"\n>>>>>>> main\n',
    '''        # Use new SSOT property
        label = log.age_week_format\n''',
    content,
    flags=re.DOTALL
)


content = re.sub(
    r'<<<<<<< HEAD\n\s*# Query editable Standard table by SSOT age_week\n\s*std_record = Standard\.query\.filter_by\(week=log\.age_week\)\.first\(\)\n\n\s*ds_egg_prod\["data"\]\.append\(create_point\(round\(d\[\'egg_prod_pct\'\], 2\)\)\)\n\s*ds_mort_f\["data"\]\.append\(create_point\(round\(mort_f, 2\)\)\)\n=======\n\s*# Query editable Standard table by exact week\n\s*std_record = Standard\.query\.filter_by\(week=\(0 if log\.age_days_total <= 0 else \(\(log\.age_days_total - 1\) // 7\) \+ 1\)\)\.first\(\)\n\s*ds_egg_prod\["data"\]\.append\(create_point\(round\(d\[\'egg_prod_pct\'\], 2\)\)\)\n\s*ds_mort_f\["data"\]\.append\(create_point\(round\(mort_f, 2\)\)\)\n>>>>>>> main\n',
    '''        # Query editable Standard table by SSOT age_week
        std_record = Standard.query.filter_by(week=log.age_week).first()

        ds_egg_prod["data"].append(create_point(round(d['egg_prod_pct'], 2)))
        ds_mort_f["data"].append(create_point(round(mort_f, 2)))\n''',
    content,
    flags=re.DOTALL
)


content = re.sub(
    r'<<<<<<< HEAD\n\n\s*# Handle \'Day 0\' Gap for Standards\n\s*if log\.age_days_total <= 0:\n\s*ds_std_egg_prod\["data"\]\.append\(create_point\(None\)\)\n\s*ds_std_mort_f\["data"\]\.append\(create_point\(None\)\)\n=======\n\s*# Standards \n\s*if log\.age_days_total <= 0:\n\s*ds_std_egg_prod\["data"\]\.append\(create_point\(None\)\)\n\s*ds_std_mort_f\["data"\]\.append\(create_point\(None\)\)\n>>>>>>> main\n',
    '''
        # Handle 'Day 0' Gap for Standards
        if log.age_days_total <= 0:
            ds_std_egg_prod["data"].append(create_point(None))
            ds_std_mort_f["data"].append(create_point(None))\n''',
    content,
    flags=re.DOTALL
)


content = re.sub(
    r'<<<<<<< HEAD\n\s*charts\[\'generalChart\'\]\[\'labels\'\] = labels\n\s*charts\[\'generalChart\'\]\[\'datasets\'\] = \[ds_egg_prod, ds_mort_f, ds_mort_m, ds_std_egg_prod, ds_std_mort_f\]\n\n\s*charts\[\'hatchingEggChart\'\]\[\'labels\'\] = labels\n\s*charts\[\'hatchingEggChart\'\]\[\'datasets\'\] = \[ds_hatch_egg, ds_std_hatch_egg\]\n=======\n\s*charts\[\'generalChart\'\]\[\'labels\'\] = labels\n\s*charts\[\'generalChart\'\]\[\'datasets\'\] = \[ds_egg_prod, ds_mort_f, ds_mort_m, ds_std_egg_prod, ds_std_mort_f\]\n\n\s*charts\[\'hatchingEggChart\'\]\[\'labels\'\] = labels\n\s*charts\[\'hatchingEggChart\'\]\[\'datasets\'\] = \[ds_hatch_egg, ds_std_hatch_egg\]\n>>>>>>> main\n',
    '''    charts['generalChart']['labels'] = labels
    charts['generalChart']['datasets'] = [ds_egg_prod, ds_mort_f, ds_mort_m, ds_std_egg_prod, ds_std_mort_f]

    charts['hatchingEggChart']['labels'] = labels
    charts['hatchingEggChart']['datasets'] = [ds_hatch_egg, ds_std_hatch_egg]\n''',
    content,
    flags=re.DOTALL
)


content = re.sub(
    r'<<<<<<< HEAD\n=======\n\s*# 5\. Current Stats \(Stock at end of last processed log\)\n\s*if daily_stats:\n\s*last = daily_stats\[-1\]\n\n>>>>>>> main\n',
    '''    # 5. Current Stats (Stock at end of last processed log)
    if daily_stats:
        last = daily_stats[-1]\n''',
    content,
    flags=re.DOTALL
)


content = re.sub(
    r'<<<<<<< HEAD\n=======\n\s*# 5\. Current Stats\n\s*if daily_stats:\n\s*last = daily_stats\[-1\]\n\s*current_stats = \{\n>>>>>>> main\n',
    '''    # 5. Current Stats
    if daily_stats:
        last = daily_stats[-1]
        current_stats = {\n''',
    content,
    flags=re.DOTALL
)

# Other general properties that shouldn't change
content = re.sub(
    r'<<<<<<< HEAD\n\s*week = 0 if delta == 0 else \(\(delta - 1\) // 7\) \+ 1 if delta > 0 else \(delta // 7\)\n=======\n\s*week = 0 if delta <= 0 else \(\(delta - 1\) // 7\) \+ 1\n>>>>>>> main\n',
    '        week = 0 if delta <= 0 else ((delta - 1) // 7) + 1\n',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'<<<<<<< HEAD\n\s*f\.current_week = 0 if days == 0 else \(\(days - 1\) // 7\) \+ 1 if days > 0 else 0\n=======\n\s*f\.current_week = 0 if days <= 0 else \(\(days - 1\) // 7\) \+ 1\n>>>>>>> main\n',
    '        f.current_week = 0 if days <= 0 else ((days - 1) // 7) + 1\n',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'<<<<<<< HEAD\n\s*age_week = 0 if age_days == 0 else \(\(age_days - 1\) // 7\) \+ 1 if age_days > 0 else \(age_days // 7\)\n=======\n\s*age_week = 0 if age_days <= 0 else \(\(age_days - 1\) // 7\) \+ 1\n>>>>>>> main\n',
    '        age_week = 0 if age_days <= 0 else ((age_days - 1) // 7) + 1\n',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'<<<<<<< HEAD\n\s*s\.age_week = 0 if diff == 0 else \(\(diff - 1\) // 7\) \+ 1 if diff > 0 else \(diff // 7\)\n=======\n\s*s\.age_week = 0 if diff <= 0 else \(\(diff - 1\) // 7\) \+ 1\n>>>>>>> main\n',
    '                s.age_week = 0 if diff <= 0 else ((diff - 1) // 7) + 1\n',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'<<<<<<< HEAD\n\s*age_week = 0 if age_days == 0 else \(\(age_days - 1\) // 7\) \+ 1 if age_days > 0 else \(age_days // 7\)\n\s*if age_week < 0: age_week = 0\n=======\n\s*age_week = 0 if age_days <= 0 else \(\(age_days - 1\) // 7\) \+ 1\n>>>>>>> main\n',
    '            age_week = 0 if age_days <= 0 else ((age_days - 1) // 7) + 1\n',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'<<<<<<< HEAD\n\s*return redirect\(url_for\(\'weight_grading\'\)\)\n=======\n\s*return redirect\(url_for\(\'health_log_bodyweight\'\)\)\n>>>>>>> main\n',
    '            return redirect(url_for(\'weight_grading\'))\n',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'<<<<<<< HEAD\n\s*age_week = \(log\.date - log\.flock\.intake_date\)\.days // 7\n=======\n\s*days_age = \(log\.date - log\.flock\.intake_date\)\.days\n\s*age_week = 0 if days_age <= 0 else \(\(days_age - 1\) // 7\) \+ 1\n>>>>>>> main\n',
    '''                days_age = (log.date - log.flock.intake_date).days
                age_week = 0 if days_age <= 0 else ((days_age - 1) // 7) + 1\n''',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'<<<<<<< HEAD\n\s*age_weeks = age_days // 7\n=======\n\s*age_weeks = 0 if age_days <= 0 else \(\(age_days - 1\) // 7\) \+ 1\n>>>>>>> main\n',
    '        age_weeks = 0 if age_days <= 0 else ((age_days - 1) // 7) + 1\n',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'<<<<<<< HEAD\n\s*hl_age_weeks = \(hl\.date - hl\.flock\.intake_date\)\.days // 7\n=======\n\s*hl_age_days = \(hl\.date - hl\.flock\.intake_date\)\.days\n\s*hl_age_weeks = 0 if hl_age_days <= 0 else \(\(hl_age_days - 1\) // 7\) \+ 1\n>>>>>>> main\n',
    '''            hl_age_days = (hl.date - hl.flock.intake_date).days
            hl_age_weeks = 0 if hl_age_days <= 0 else ((hl_age_days - 1) // 7) + 1\n''',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'<<<<<<< HEAD\n\s*f\.age_weeks = 0 if days_age == 0 else \(\(days_age - 1\) // 7\) \+ 1 if days_age > 0 else 0\n\s*f\.age_days = \(\(days_age - 1\) % 7\) \+ 1 if days_age > 0 else 0\n\s*f\.current_week = 0 if days_age == 0 else \(\(days_age - 1\) // 7\) \+ 1 if days_age > 0 else 0\n=======\n\s*f\.age_weeks = 0 if days_age <= 0 else \(\(days_age - 1\) // 7\) \+ 1\n\s*f\.age_days = \(\(days_age - 1\) % 7\) \+ 1 if days_age > 0 else 0\n\s*f\.current_week = 0 if days_age <= 0 else \(\(days_age - 1\) // 7\) \+ 1\n>>>>>>> main\n',
    '''        f.age_weeks = 0 if days_age <= 0 else ((days_age - 1) // 7) + 1
        f.age_days = ((days_age - 1) % 7) + 1 if days_age > 0 else 0
        f.current_week = 0 if days_age <= 0 else ((days_age - 1) // 7) + 1\n''',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'<<<<<<< HEAD\n\s*\'age_week_day\': d\.get\(\'log\'\)\.age_week_format if d\.get\(\'log\'\) else None,\n=======\n\s*\'week_day_format\': d\.get\(\'week_day_format\'\),\n>>>>>>> main\n',
    "                    'age_week_day': d.get('log').age_week_format if d.get('log') else None,\n",
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'<<<<<<< HEAD\n\s*\'age_week_day\': log_obj\.age_week_format,\n=======\n\s*\'week_day_format\': d\.get\(\'week_day_format\'\),\n>>>>>>> main\n',
    "                            'age_week_day': log_obj.age_week_format,\n",
    content,
    flags=re.DOTALL
)

with open('app.py', 'w') as f:
    f.write(content)
