import re

with open('app.py', 'r') as f:
    content = f.read()

# Let's see where calculate_flock_summary is used
print(re.findall(r'calculate_flock_summary\(.*?\)', content))
