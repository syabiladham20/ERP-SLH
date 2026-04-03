import re

with open('analytics.py', 'r') as f:
    content = f.read()

pattern = r'<<<<<<< HEAD\n                "age_week": log\.age_week,\n=======\n                "age_week": \(log\.date - log\.flock\.intake_date\)\.days // 7 \+ 1,\n>>>>>>> fix/color-contrast-orange-6176072627711246685'
replacement = r'                "age_week": log.age_week,'

new_content = re.sub(pattern, replacement, content)

with open('analytics.py', 'w') as f:
    f.write(new_content)
