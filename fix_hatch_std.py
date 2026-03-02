import re

with open('templates/flock_detail_readonly.html', 'r') as f:
    content = f.read()

# Let's check `renderHatchChart` in flock_detail_readonly.html
match = re.search(r'function renderHatchChart\(\).*?\}\s*\}', content, re.DOTALL)
if match:
    pass
