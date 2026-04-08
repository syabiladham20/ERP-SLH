import re

with open('app.py', 'r') as f:
    content = f.read()

# I already created `get_flock_dashboard_payload(flock)` in app.py in the previous patch.
# I just need to update `flock_detail`, `executive_flock_detail`, and `flock_detail_modern` to use it
# and remove their inline generation of chart_data and chart_data_weekly.

# Let's write a function to apply this to a specific route code.
def replace_inline_with_helper(content, route_name):
    start_fd = content.find(f"def {route_name}(id):")
    if start_fd == -1: return content

    start_cd = content.find("chart_data = {", start_fd)
    end_cdw = content.find("    # 5. Current Stats", start_cd)

    if start_cd == -1 or end_cdw == -1: return content

    # We replace everything from `chart_data = {` up to `    # 5. Current Stats`
    # with:
    # payload = get_flock_dashboard_payload(flock)
    # chart_data = payload['daily']
    # chart_data_weekly = payload['weekly']

    replacement = """payload = get_flock_dashboard_payload(flock)
    chart_data = payload['daily']
    chart_data_weekly = payload['weekly']

"""
    return content[:start_cd] + replacement + content[end_cdw:]

content = replace_inline_with_helper(content, 'flock_detail')
content = replace_inline_with_helper(content, 'flock_detail_modern')
content = replace_inline_with_helper(content, 'executive_flock_detail')

with open('app.py', 'w') as f:
    f.write(content)
