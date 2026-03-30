import re

with open('app.py', 'r') as f:
    content = f.read()

# Fix recursion
fix = """
def safe_commit():
    try:
        db.session.commit()
        return True
    except Exception as e:
"""

content = content.replace("def safe_commit():\n    try:\n        safe_commit()\n        return True\n    except Exception as e:", fix)

with open('app.py', 'w') as f:
    f.write(content)
