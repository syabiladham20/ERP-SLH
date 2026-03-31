import re

with open('templates/admin/users.html', 'r') as f:
    content = f.read()

# Pattern to match git merge conflict markers and keep the HEAD side
# We want to keep the name fields which are in the HEAD side, which looks like this:
# <<<<<<< HEAD
# content
# =======
# >>>>>>> origin/branch

# Actually, the file has exactly:
# <<<<<<< HEAD
# (content we want)
# =======
# >>>>>>> origin/jules-audit-app-py-flask-login-13580675729170186842
#
# Wait, some lines have the ======= immediately followed by >>>>>>> on the next line or same line.
# Let's write a simpler string replacement.

lines = content.split('\n')
new_lines = []
skip = False
for line in lines:
    if line.startswith('<<<<<<< HEAD'):
        continue
    if line.startswith('======='):
        skip = True
        continue
    if line.startswith('>>>>>>> origin/'):
        skip = False
        continue

    if not skip:
        new_lines.append(line)

with open('templates/admin/users.html', 'w') as f:
    f.write('\n'.join(new_lines))
