import re
with open('templates/flock_detail_readonly.html', 'r') as f:
    content = f.read()

start = content.find("function renderHatchChart()")
end = content.find("  function showNoteModal", start)
if start != -1:
    print(content[start+1000:start+2500])
