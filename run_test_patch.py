import re

with open("app.py", "r") as f:
    content = f.read()

# Replace bodyweight_logs json passing
# {{ bodyweight_logs | tojson | safe }} will error if bodyweight_logs contains datetime objects.
# We need to ensure bodyweight_logs uses strings for dates, or we parse it properly.
# We can fix this in `app.py` when building `bodyweight_logs`.

replacement = """        bodyweight_logs.append({
            'log_id': log.id,
            'house_name': log.flock.house.name,
            'house_id': log.flock.house_id,
            'age_weeks': age_weeks,
            'date': log.date.strftime('%Y-%m-%d'),
            'std_m': log.standard_bw_male or 0,
            'std_f': log.standard_bw_female or 0,"""

content = re.sub(r"        bodyweight_logs\.append\(\{.*?            'date': log\.date,.*?            'std_f': log\.standard_bw_female or 0,", replacement, content, flags=re.DOTALL)

with open("app.py", "w") as f:
    f.write(content)
