import re
with open('templates/flock_detail.html', 'r') as f:
    content = f.read()

start = content.find("waterChart = new Chart(")
end = content.find("  }", start) + 4
print(content[start:end])
