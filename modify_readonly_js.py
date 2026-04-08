import re

with open('templates/flock_detail_readonly.html', 'r') as f:
    content = f.read()

# Replace variables
content = content.replace("const chartDataDaily = {{ chart_data | tojson }};", "")
content = content.replace("const chartDataWeekly = {{ chart_data_weekly | tojson }};", "")

# Find where initCharts is called, or where charts are rendered
# It's likely document.addEventListener('DOMContentLoaded', ...) or initCharts()
# We need to wrap it in a fetch call.

with open('templates/flock_detail_readonly.html', 'w') as f:
    f.write(content)
