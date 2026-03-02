import re
with open('templates/flock_detail.html', 'r') as f:
    content = f.read()

start = content.find("function renderHatchChart()")
end = content.find("  function showNoteModal", start)
if start != -1:
    print(content[start+3000:start+4500])
