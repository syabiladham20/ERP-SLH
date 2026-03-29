import re

with open("app.py", "r") as f:
    content = f.read()

# Make sure we don't have tuple or date issues with tojson
# `reports_map` has tuple keys which might not serialize correctly but we don't pass `reports_map` to frontend directly.
# Let's manually replace the date mapping if it failed in previous regex.

new_content = []
lines = content.split('\n')
for i, line in enumerate(lines):
    if "            'date': log.date," in line:
        line = "            'date': log.date.strftime('%Y-%m-%d'),"
    new_content.append(line)

with open("app.py", "w") as f:
    f.write('\n'.join(new_content))
