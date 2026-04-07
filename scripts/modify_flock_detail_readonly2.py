import re

with open('templates/flock_detail_readonly.html', 'r') as f:
    content = f.read()

# Make sure fetchAndRenderCharts() is called in DOMContentLoaded
pattern = re.compile(r"document\.addEventListener\('DOMContentLoaded', \(\) => \{\n(.*?)// Update \"Switch House\" links with current hash", re.DOTALL)
def replace_dom_ready(match):
    return "document.addEventListener('DOMContentLoaded', () => {\n      fetchAndRenderCharts();\n" + match.group(1) + "// Update \"Switch House\" links with current hash"

content = pattern.sub(replace_dom_ready, content)

with open('templates/flock_detail_readonly.html', 'w') as f:
    f.write(content)
