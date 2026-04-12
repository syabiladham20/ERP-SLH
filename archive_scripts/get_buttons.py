import re

with open('templates/flock_detail.html', 'r') as f:
    content = f.read()

# Let's search for the logic of the label toggle buttons
matches = re.finditer(r'toggle\w*Labels.*?\}', content, re.DOTALL)
for m in matches:
    print(m.group(0))

print("--- JS function for toggle ---")
match = re.search(r'function toggle\w*DataLabels\([^)]*\)\s*\{[^}]*\}', content, re.DOTALL)
if match:
    print(match.group(0))
