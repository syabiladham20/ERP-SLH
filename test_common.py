import re

with open('templates/flock_detail.html', 'r') as f:
    content = f.read()

# Inspect commonOptions completely
match = re.search(r'const commonOptions\s*=\s*\{.*?\};', content, re.DOTALL)
if match:
    print("Found commonOptions in flock_detail.html:")
    print(match.group(0))

with open('templates/flock_detail_readonly.html', 'r') as f:
    content2 = f.read()

match2 = re.search(r'const commonOptions\s*=\s*\{.*?\};', content2, re.DOTALL)
if match2:
    print("\nFound commonOptions in flock_detail_readonly.html:")
    print(match2.group(0))
