import re

with open('app.py', 'r') as f:
    content = f.read()

# Let's verify _generate_chart_payload logic specifically datalabels
match = re.search(r'def init_dataset.*?return ds', content, re.DOTALL)
if match:
    print(match.group(0))
