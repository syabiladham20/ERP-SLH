import re

with open('app.py', 'r') as f:
    app_content = f.read()

with open('app.py.bak', 'r') as f:
    app_bak_content = f.read()

# Get the old function
old_func_match = re.search(r'def calculate_flock_summary\(flock, daily_stats\):.*?return dashboard_metrics, summary_table', app_bak_content, re.DOTALL)
if old_func_match:
    old_func = old_func_match.group(0)
else:
    print("Old func not found")
    exit(1)

# Get the new function
new_func_match = re.search(r'def calculate_flock_summary\(flock, daily_stats\):.*?return summary_dashboard, summary_table', app_content, re.DOTALL)
if new_func_match:
    new_func = new_func_match.group(0)
else:
    print("New func not found")
    exit(1)

app_content = app_content.replace(new_func, old_func)

with open('app.py', 'w') as f:
    f.write(app_content)

print("Replaced successfully")
