import re
with open('templates/flock_detail.html', 'r') as f:
    content = f.read()

match = re.search(r'waterChart\s*=\s*new\s*Chart.*?options:\s*\{(.*?)\}\s*\}[,\)]', content, re.DOTALL)
if match:
    print(match.group(1))
