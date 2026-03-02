import re
with open('templates/flock_detail.html', 'r') as f:
    content = f.read()

start = content.find("function renderHatchChart()")
if start != -1:
    datasets_start = content.find("datasets: [", start)
    datasets_end = content.find("          options: {", datasets_start)
    print(content[datasets_start:datasets_end])
