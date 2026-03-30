import re

with open('app.py', 'r') as f:
    content = f.read()

# We will find `        active_flocks.sort(` and prepend `    if active_flocks:\n`
# First, remove any blank lines where `if active_flocks:` used to be. (It's already empty strings from sed)
# Let's just match `        active_flocks.sort` and replace with `    if active_flocks:\n        active_flocks.sort`
# But wait, we have `        inactive_flocks.sort` and `        flocks.sort` too.
# Let's carefully fix it globally.

# Reset any broken indents
content = re.sub(r'^[ \t]*active_flocks\.sort\(', r'    active_flocks.sort(', content, flags=re.MULTILINE)
content = re.sub(r'^[ \t]*inactive_flocks\.sort\(', r'    inactive_flocks.sort(', content, flags=re.MULTILINE)
content = re.sub(r'^[ \t]*flocks\.sort\(', r'    flocks.sort(', content, flags=re.MULTILINE)

# Remove any orphaned `if active_flocks:` that might have survived the sed
content = re.sub(r'^[ \t]*if active_flocks:[ \t]*\n', '', content, flags=re.MULTILINE)
content = re.sub(r'^[ \t]*if inactive_flocks:[ \t]*\n', '', content, flags=re.MULTILINE)
content = re.sub(r'^[ \t]*if flocks:[ \t]*\n', '', content, flags=re.MULTILINE)


content = re.sub(r'^[ \t]*active_flocks\.sort\(', r'    if active_flocks:\n        active_flocks.sort(', content, flags=re.MULTILINE)
content = re.sub(r'^[ \t]*inactive_flocks\.sort\(', r'    if inactive_flocks:\n        inactive_flocks.sort(', content, flags=re.MULTILINE)
content = re.sub(r'^[ \t]*flocks\.sort\(', r'    if flocks:\n        flocks.sort(', content, flags=re.MULTILINE)

with open('app.py', 'w') as f:
    f.write(content)
