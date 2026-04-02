import re

with open('app.py.bak', 'r') as f:
    content = f.read()

# Apply the API Endpoint fix
with open('modify_app_api.py', 'r') as f:
    api_script = f.read()
pattern = re.compile(r'def get_chart_data\(flock_id\):.*?return data\n', re.DOTALL)
new_get_chart_data = api_script.split('new_get_chart_data = """')[1].split('"""')[0]
content = pattern.sub(new_get_chart_data, content)


# Remove chart_data injections
# find 'return render_template('flock_detail_modern.html', ... chart_data=chart_data, chart_data_weekly=chart_data_weekly ...)'
content = re.sub(r',\s*chart_data=chart_data', '', content)
content = re.sub(r',\s*chart_data_weekly=chart_data_weekly', '', content)

# But we also have to delete the HUGE blocks that generate chart_data to save performance!
# def executive_flock_detail(id): ... chart_data = { ... } ... chart_data_weekly = { ... }
# Let's locate them.

# First block: executive_flock_detail
# Lines roughly 9394-9630 (in the backup)
# We can use regex to remove 'chart_data = {' up to '# 4. Chart Data (Weekly)'
# Then remove 'chart_data_weekly = {' up to 'return render_template'
# Actually, since python parses it block by block, we can just replace the assignment blocks with `pass` or delete them.

def strip_chart_generation(text):
    # Regex to find `chart_data = { ... }` up to the end of the `for d in daily_stats:` loop that follows it
    # We'll just look for `# 3. Chart Data (Daily)` and remove everything until `return render_template`
    # and do the same for view_flock

    # 1. view_flock
    text = re.sub(r'# 3\. Chart Data \(Daily\).*?return render_template\(\'flock_detail_modern\.html\'',
                  r'return render_template(\'flock_detail_modern.html\'', text, flags=re.DOTALL)

    # 2. executive_flock_detail
    text = re.sub(r'# 3\. Chart Data \(Daily\).*?return render_template\(\'flock_detail_readonly\.html\'',
                  r'return render_template(\'flock_detail_readonly.html\'', text, flags=re.DOTALL)

    return text

content = strip_chart_generation(content)

with open('app.py', 'w') as f:
    f.write(content)
