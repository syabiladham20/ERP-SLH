with open("app.py", "r") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else ''))" in line and "logs = query.order_by(DailyLog.date.desc()).all()" in lines[i-2]:
        lines.insert(i, "    active_flocks = Flock.query.filter_by(status='Active').all()\n")
        break

with open("app.py", "w") as f:
    f.writelines(lines)
