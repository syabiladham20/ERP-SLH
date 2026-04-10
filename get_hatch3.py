with open('templates/flock_detail_readonly.html', 'r') as f:
    content = f.read()

start = content.find("function renderHatchChart()")
if start != -1:
    end = content.find("  // Initial Render", start)
    print(content[start:start+1000])
