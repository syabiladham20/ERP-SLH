import re

with open("templates/flock_form.html", "r") as f:
    content = f.read()

search = """            <label for="farm_name" class="form-label">Farm Name</label>"""
replace = """            <label for="farm_name" class="form-label required">Farm Name</label>"""

if search in content:
    content = content.replace(search, replace)
    with open("templates/flock_form.html", "w") as f:
        f.write(content)
    print("Patched label in flock_form.html successfully.")
