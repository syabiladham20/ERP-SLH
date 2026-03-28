import re

with open("tests.py", "r") as f:
    content = f.read()

# Replace any instance of self.app.post('/flocks', data={'house_name': 'X', 'intake_date': 'Y'})
# with self.app.post('/flocks', data={'farm_name': 'Farm 1', 'house_name': 'X', 'intake_date': 'Y'})

content = re.sub(
    r"self\.app\.post\('/flocks', data=\{'house_name': '([^']+)', 'intake_date': '([^']+)'\}\)",
    r"self.app.post('/flocks', data={'farm_name': 'Farm 1', 'house_name': '\1', 'intake_date': '\2'})",
    content
)

with open("tests.py", "w") as f:
    f.write(content)

print("Patched tests.py")
