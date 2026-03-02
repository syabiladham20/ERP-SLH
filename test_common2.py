import re

with open('templates/flock_detail.html', 'r') as f:
    content = f.read()

# Let's see the error in commonOptions in flock_detail.html
match = re.search(r'const commonOptions\s*=\s*\{.*?\};\n\n', content, re.DOTALL)
if match:
    print("Found commonOptions in flock_detail.html:")
    print(match.group(0))
