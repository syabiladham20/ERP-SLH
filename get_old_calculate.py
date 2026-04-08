import re

with open('app.py.bak', 'r') as f:
    lines = f.readlines()

in_func = False
for line in lines:
    if line.startswith('def calculate_flock_summary'):
        in_func = True
    if in_func:
        print(line, end='')
        if line.startswith('def _generate_chart_payload') or line.startswith('def view_flock'):
            break
