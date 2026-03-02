import re

with open('templates/flock_detail.html', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'const commonOptions =' in line:
        start = i
        break

for i in range(start, start + 60):
    print(f"{i+1}: {lines[i]}", end='')
