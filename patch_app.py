import re

with open('app.py', 'r') as f:
    content = f.read()

# Pattern 1: f.current_week = 0 if days <= 0 else ((days - 1) // 7) + 1
content = re.sub(
    r'<<<<<<< HEAD\n        f\.current_week = 0 if days <= 0 else \(\(days - 1\) // 7\) \+ 1\n=======\n        f\.current_week = 0 if days == 0 else \(\(days - 1\) // 7\) \+ 1 if days > 0 else 0\n>>>>>>> fix/color-contrast-orange-6176072627711246685',
    r'        f.current_week = 0 if days <= 0 else ((days - 1) // 7) + 1',
    content
)

# Pattern 2: f.age_weeks, f.age_days, f.current_week
content = re.sub(
    r'<<<<<<< HEAD\n        f\.age_weeks = 0 if days_age <= 0 else \(\(days_age - 1\) // 7\) \+ 1\n        f\.age_days = \(\(days_age - 1\) % 7\) \+ 1 if days_age > 0 else 0\n        f\.current_week = 0 if days_age <= 0 else \(\(days_age - 1\) // 7\) \+ 1\n=======\n        f\.age_weeks = 0 if days_age == 0 else \(\(days_age - 1\) // 7\) \+ 1 if days_age > 0 else 0\n        f\.age_days = \(\(days_age - 1\) % 7\) \+ 1 if days_age > 0 else 0\n        f\.current_week = 0 if days_age == 0 else \(\(days_age - 1\) // 7\) \+ 1 if days_age > 0 else 0\n>>>>>>> fix/color-contrast-orange-6176072627711246685',
    r'        f.age_weeks = 0 if days_age <= 0 else ((days_age - 1) // 7) + 1\n        f.age_days = ((days_age - 1) % 7) + 1 if days_age > 0 else 0\n        f.current_week = 0 if days_age <= 0 else ((days_age - 1) // 7) + 1',
    content
)

# Pattern 3: current_stats in api_weekly_data
content = re.sub(
    r'<<<<<<< HEAD\n    # 5\. Current Stats\n    if daily_stats:\n        last = daily_stats\[-1\]\n        current_stats = {\n            \'male_prod\': last\.get\(\'stock_male_prod_end\', 0\),\n            \'female_prod\': last\.get\(\'stock_female_prod_end\', 0\),\n            \'male_hosp\': last\.get\(\'stock_male_hosp_end\', 0\),\n            \'female_hosp\': last\.get\(\'stock_female_hosp_end\', 0\),\n            \'male_ratio\': last\[\'male_ratio_stock\'\] if last\.get\(\'male_ratio_stock\'\) else 0\n        }\n=======\n    # 5\. Current Stats \(Stock at end of last processed log\)\n    if daily_stats:\n        last = daily_stats\[-1\]\n\n        current_stats = {\n            \'male_prod\': last\.get\(\'stock_male_prod_end\', 0\),\n            \'female_prod\': last\.get\(\'stock_female_prod_end\', 0\),\n            \'male_hosp\': last\.get\(\'stock_male_hosp_end\', 0\),\n            \'female_hosp\': last\.get\(\'stock_female_hosp_end\', 0\),\n            \'male_ratio\': last\[\'male_ratio_stock\'\] if last\.get\(\'male_ratio_stock\'\) else 0\n        }\n>>>>>>> fix/color-contrast-orange-6176072627711246685',
    r'    # 5. Current Stats\n    if daily_stats:\n        last = daily_stats[-1]\n        current_stats = {\n            \'male_prod\': last.get(\'stock_male_prod_end\', 0),\n            \'female_prod\': last.get(\'stock_female_prod_end\', 0),\n            \'male_hosp\': last.get(\'stock_male_hosp_end\', 0),\n            \'female_hosp\': last.get(\'stock_female_hosp_end\', 0),\n            \'male_ratio\': last[\'male_ratio_stock\'] if last.get(\'male_ratio_stock\') else 0\n        }',
    content
)


# Pattern 4: age_week in age_calculation
content = re.sub(
    r'<<<<<<< HEAD\n            age_week = 0 if age_days <= 0 else \(\(age_days - 1\) // 7\) \+ 1\n=======\n            age_week = 0 if age_days == 0 else \(\(age_days - 1\) // 7\) \+ 1 if age_days > 0 else \(age_days // 7\)\n            if age_week < 0: age_week = 0\n>>>>>>> fix/color-contrast-orange-6176072627711246685',
    r'            age_week = 0 if age_days <= 0 else ((age_days - 1) // 7) + 1',
    content
)

# Pattern 5: Invalid date format redirect
content = re.sub(
    r'<<<<<<< HEAD\n            return redirect\(url_for\(\'health_log_bodyweight\'\)\)\n=======\n            return redirect\(url_for\(\'weight_grading\'\)\)\n>>>>>>> fix/color-contrast-orange-6176072627711246685',
    r'            return redirect(url_for(\'health_log_bodyweight\'))',
    content
)

# Pattern 6: days_age and age_week inside push alert
content = re.sub(
    r'<<<<<<< HEAD\n                days_age = \(log\.date - log\.flock\.intake_date\)\.days\n                age_week = 0 if days_age <= 0 else \(\(days_age - 1\) // 7\) \+ 1\n=======\n                age_week = \(log\.date - log\.flock\.intake_date\)\.days // 7\n>>>>>>> fix/color-contrast-orange-6176072627711246685',
    r'                days_age = (log.date - log.flock.intake_date).days\n                age_week = 0 if days_age <= 0 else ((days_age - 1) // 7) + 1',
    content
)

# Pattern 7: log.date - log.flock.intake_date
content = re.sub(
    r'<<<<<<< HEAD\n        age_weeks = 0 if age_days <= 0 else \(\(age_days - 1\) // 7\) \+ 1\n=======\n        age_weeks = age_days // 7\n>>>>>>> fix/color-contrast-orange-6176072627711246685',
    r'        age_weeks = 0 if age_days <= 0 else ((age_days - 1) // 7) + 1',
    content
)

# Pattern 8: hl.date - hl.flock.intake_date
content = re.sub(
    r'<<<<<<< HEAD\n            hl_age_days = \(hl\.date - hl\.flock\.intake_date\)\.days\n            hl_age_weeks = 0 if hl_age_days <= 0 else \(\(hl_age_days - 1\) // 7\) \+ 1\n=======\n            hl_age_weeks = \(hl\.date - hl\.flock\.intake_date\)\.days // 7\n>>>>>>> fix/color-contrast-orange-6176072627711246685',
    r'            hl_age_days = (hl.date - hl.flock.intake_date).days\n            hl_age_weeks = 0 if hl_age_days <= 0 else ((hl_age_days - 1) // 7) + 1',
    content
)

# Pattern 9: age_days and age_week
content = re.sub(
    r'<<<<<<< HEAD\n            age_week = 0 if age_days <= 0 else \(\(age_days - 1\) // 7\) \+ 1\n=======\n            age_week = 0 if age_days == 0 else \(\(age_days - 1\) // 7\) \+ 1 if age_days > 0 else \(age_days // 7\)\n>>>>>>> fix/color-contrast-orange-6176072627711246685',
    r'            age_week = 0 if age_days <= 0 else ((age_days - 1) // 7) + 1',
    content
)

# Pattern 10: delta and week
content = re.sub(
    r'<<<<<<< HEAD\n        week = 0 if delta <= 0 else \(\(delta - 1\) // 7\) \+ 1\n=======\n        week = 0 if delta == 0 else \(\(delta - 1\) // 7\) \+ 1 if delta > 0 else \(delta // 7\)\n>>>>>>> fix/color-contrast-orange-6176072627711246685',
    r'        week = 0 if delta <= 0 else ((delta - 1) // 7) + 1',
    content
)

# Pattern 11: diff and s.age_week
content = re.sub(
    r'<<<<<<< HEAD\n                s\.age_week = 0 if diff <= 0 else \(\(diff - 1\) // 7\) \+ 1\n=======\n                s\.age_week = 0 if diff == 0 else \(\(diff - 1\) // 7\) \+ 1 if diff > 0 else \(diff // 7\)\n>>>>>>> fix/color-contrast-orange-6176072627711246685',
    r'                s.age_week = 0 if diff <= 0 else ((diff - 1) // 7) + 1',
    content
)

with open('app.py', 'w') as f:
    f.write(content)
