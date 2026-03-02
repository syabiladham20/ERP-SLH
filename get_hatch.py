import re
with open('templates/flock_detail_readonly.html', 'r') as f:
    content = f.read()

match = re.search(r'function renderHatchChart\(\) \{.*?(?=function switchMode)', content, re.DOTALL)
if match:
    pass
