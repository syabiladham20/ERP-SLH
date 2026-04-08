import re

with open('app.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'def calculate_flock_summary' in line:
        for j in range(i, i + 50):
            print(lines[j], end='')
        break
