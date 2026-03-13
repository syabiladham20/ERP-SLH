import re

with open('app.py', 'r') as f:
    content = f.read()

content = content.replace("rearing_flocks = [f for f in active_flocks if f.phase == 'Rearing']", "rearing_flocks = [f for f in active_flocks if f.phase in ['Brooding', 'Growing']]")

with open('app.py', 'w') as f:
    f.write(content)
