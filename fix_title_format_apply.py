import re

with open('templates/flock_detail.html', 'r') as f:
    content = f.read()

# Let's modify the chart titles dynamically at generation
match = re.search(r'function updateChartTitle.*?\}', content, re.DOTALL)
if match:
    # Just to verify our regex worked.
    pass
