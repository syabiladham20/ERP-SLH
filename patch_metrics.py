import re

with open('metrics.py', 'r') as f:
    content = f.read()

# Pattern 1:
content = re.sub(
    r'<<<<<<< HEAD\n        if log\.age_days_total <= 0:\n            continue\n\n=======\n>>>>>>> fix/color-contrast-orange-6176072627711246685\n',
    r'        if log.age_days_total <= 0:\n            continue\n\n',
    content
)

# Pattern 2: Production Week Calculation
content = re.sub(
    r'<<<<<<< HEAD\n        bio_week = log\.age_week\n        prod_week = None\n        if flock\.start_of_lay_date:\n            start_days = \(flock\.start_of_lay_date - flock\.intake_date\)\.days\n            start_bio_week = 0 if start_days <= 0 else \(\(start_days - 1\) // 7\) \+ 1\n=======\n        bio_days = \(log\.date - flock\.intake_date\)\.days\n        bio_week = 0 if bio_days == 0 else \(\(bio_days - 1\) // 7\) \+ 1 if bio_days > 0 else \(bio_days // 7\)\n        prod_week = None\n        if flock\.start_of_lay_date:\n            start_days = \(flock\.start_of_lay_date - flock\.intake_date\)\.days\n            start_bio_week = 0 if start_days == 0 else \(\(start_days - 1\) // 7\) \+ 1 if start_days > 0 else \(start_days // 7\)\n>>>>>>> fix/color-contrast-orange-6176072627711246685',
    r'        bio_week = log.age_week\n        prod_week = None\n        if flock.start_of_lay_date:\n            start_days = (flock.start_of_lay_date - flock.intake_date).days\n            start_bio_week = 0 if start_days <= 0 else ((start_days - 1) // 7) + 1',
    content
)

# Pattern 3: Metrics Dict
content = re.sub(
    r'<<<<<<< HEAD\n            \'week_day_format\': log\.age_week_format,\n            \'production_week\': prod_week,\n            \'age_days\': log\.age_days_total,\n=======\n            \'production_week\': prod_week,\n            \'age_days\': \(log\.date - flock\.intake_date\)\.days,\n>>>>>>> fix/color-contrast-orange-6176072627711246685',
    r'            \'week_day_format\': log.age_week_format,\n            \'production_week\': prod_week,\n            \'age_days\': log.age_days_total,',
    content
)

with open('metrics.py', 'w') as f:
    f.write(content)
