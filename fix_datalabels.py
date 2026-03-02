import re

# I already implemented the _showLabels feature dynamically in fix_charts_script.py!
# But let's check if there are any remaining `datalabels:` inside datasets that are not removed.

def check_datalabels(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    matches = re.finditer(r'datalabels\s*:', content)
    print(f"Checking {filepath}")
    for m in matches:
        start = m.start() - 50
        end = m.end() + 50
        print(content[start:end].replace('\n', ' '))

check_datalabels('templates/flock_detail.html')
check_datalabels('templates/flock_detail_readonly.html')
