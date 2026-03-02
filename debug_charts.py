import re

with open('templates/flock_detail.html', 'r') as f:
    content = f.read()

# Let's check `...scales` what is it?
match = re.search(r'const\s+scales\s*=\s*(.*?);', content, re.DOTALL)
if match:
    print("Found scales:")
    print(match.group(0)[:200])
else:
    print("Scales not found!")

# Same for Feed, Male, Female
match = re.search(r'const\s+feedScales\s*=\s*(.*?);', content, re.DOTALL)
if match:
    print("Found feedScales:")
    print(match.group(0)[:200])
