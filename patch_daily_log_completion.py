with open("app.py", "r") as f:
    content = f.read()

import re

search = """def check_daily_log_completion(farm_id, selected_date):
    \"\"\"
    Checks the DailyLog table for the current farm_id and selected_date.
    Returns a list of dictionaries with house info and completion status.
    \"\"\"
    if not farm_id or not selected_date:
        return []

    # Get all active flocks for the given farm
    active_flocks = Flock.query.join(House).filter(
        Flock.farm_id == farm_id,
        Flock.status == 'Active'
    ).order_by(House.name).all()"""

replace = """def check_daily_log_completion(farm_id, selected_date):
    \"\"\"
    Checks the DailyLog table for the current farm_id and selected_date.
    Returns a list of dictionaries with house info and completion status.
    If farm_id is None, returns all active flocks across the entire system.
    \"\"\"
    if not selected_date:
        return []

    # Get active flocks for the given farm, or all active flocks if farm_id is None
    query = Flock.query.join(House).filter(Flock.status == 'Active')
    if farm_id:
        query = query.filter(Flock.farm_id == farm_id)

    active_flocks = query.order_by(House.name).all()"""

if search in content:
    content = content.replace(search, replace)
    with open("app.py", "w") as f:
        f.write(content)
    print("Patched app.py successfully.")
else:
    print("Could not find the target codeblock in app.py")
