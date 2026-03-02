import re

with open('templates/flock_detail.html', 'r') as f:
    content = f.read()

# Let's inspect updateChartTitle function
match = re.search(r'function updateChartTitle.*?\}', content, re.DOTALL)
if match:
    print(match.group(0))
