import re

with open('analytics.py', 'r') as f:
    content = f.read()

content = re.sub(
    r'<<<<<<< HEAD\n\s*"age_week": \(log\.date - log\.flock\.intake_date\)\.days // 7 \+ 1,\n=======\n\s*"age_week": log\.age_week,\n>>>>>>> main\n',
    '                "age_week": log.age_week,\n',
    content,
    flags=re.DOTALL
)

with open('analytics.py', 'w') as f:
    f.write(content)
