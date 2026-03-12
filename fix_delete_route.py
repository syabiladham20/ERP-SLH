import re

with open('app.py', 'r') as f:
    content = f.read()

target = """    db.session.delete(log)
    db.session.commit()
    flash("Daily Log deleted.", "info")"""

replacement = """    db.session.delete(log)
    db.session.commit()
    recalculate_flock_inventory(flock_id)
    update_flock_phase(flock_id)
    flash("Daily Log deleted.", "info")"""

content = content.replace(target, replacement)
with open('app.py', 'w') as f:
    f.write(content)
