import re

with open('app.py', 'r') as f:
    content = f.read()

# Replace active_flocks.sort(...) with if active_flocks: active_flocks.sort(...)
# We can use regex.
content = re.sub(r'^[ \t]*active_flocks\.sort\(key=lambda x: natural_sort_key\(x\.house\.name if x\.house else \'\'\)\)',
                 r'    if active_flocks:\n        active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else \'\'))',
                 content, flags=re.MULTILINE)

# Similar for other sorts
content = re.sub(r'^[ \t]*inactive_flocks\.sort\(', r'    if inactive_flocks:\n        inactive_flocks.sort(', content, flags=re.MULTILINE)
content = re.sub(r'^[ \t]*flocks\.sort\(', r'    if flocks:\n        flocks.sort(', content, flags=re.MULTILINE)

with open('app.py', 'w') as f:
    f.write(content)
