import re

with open("templates/flock_form.html", "r") as f:
    content = f.read()

search = """            <input class="form-control" list="farmOptions" id="farm_name" name="farm_name" placeholder="Type to search or add new...">"""

replace = """            <input class="form-control" list="farmOptions" id="farm_name" name="farm_name" placeholder="Type to search or add new..." required>"""

if search in content:
    content = content.replace(search, replace)
    with open("templates/flock_form.html", "w") as f:
        f.write(content)
    print("Patched flock_form.html successfully.")
else:
    print("Could not find the target codeblock in flock_form.html")
