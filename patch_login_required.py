import re

with open('app.py', 'r') as f:
    content = f.read()

# Prepend @login_required to @dept_required if not already there
# We use regex to find @dept_required
# and check if the previous line is @login_required

lines = content.split('\n')
new_lines = []

for i, line in enumerate(lines):
    if '@dept_required' in line:
        if i > 0 and '@login_required' not in lines[i-1]:
            new_lines.append('@login_required')
    new_lines.append(line)

with open('app.py', 'w') as f:
    f.write('\n'.join(new_lines))

print("Patch applied.")
