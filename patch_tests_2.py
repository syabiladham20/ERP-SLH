import re

with open("tests.py", "r") as f:
    content = f.read()

# Make sure all occurrences of data={ inside self.app.post('/flocks' have 'farm_name': 'Farm 1'

content = re.sub(
    r"(self\.app\.post\('/flocks',\s*data=\{)(?!'farm_name')",
    r"\1'farm_name': 'Farm 1', ",
    content
)

with open("tests.py", "w") as f:
    f.write(content)

print("Patched tests.py")
