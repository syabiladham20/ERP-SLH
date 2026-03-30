import re

with open('app.py', 'r') as f:
    content = f.read()

# Replace all .all() that do NOT have joinedload(Flock.house) but query Flock with options(joinedload(Flock.house))
# We will just manually replace the specific lines identified to be safe.

replacements = {
    "active_flocks = Flock.query.filter_by(status='Active', phase='Production').all()":
    "active_flocks = Flock.query.options(joinedload(Flock.house)).filter_by(status='Active', phase='Production').all()",

    "active_flocks = Flock.query.filter_by(status='Active').all()":
    "active_flocks = Flock.query.options(joinedload(Flock.house)).filter_by(status='Active').all()",

    "flocks = Flock.query.order_by(Flock.intake_date.desc()).all()":
    "flocks = Flock.query.options(joinedload(Flock.house)).order_by(Flock.intake_date.desc()).all()",

    "all_flocks = Flock.query.order_by(Flock.intake_date.desc()).all()":
    "all_flocks = Flock.query.options(joinedload(Flock.house)).order_by(Flock.intake_date.desc()).all()"
}

for old, new in replacements.items():
    content = content.replace(old, new)

with open('app.py', 'w') as f:
    f.write(content)
