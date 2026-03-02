import re

with open('templates/flock_detail.html', 'r') as f:
    content = f.read()

# Let's check for the datalabels plugin inside the chart configurations.
print("Datalabels plugin setup:")
matches = re.finditer(r'plugins:\s*\{[^}]*datalabels:[^}]*\}', content, re.DOTALL)
for m in matches:
    print(m.group(0))
