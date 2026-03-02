import re
with open('templates/flock_detail_readonly.html', 'r') as f:
    content = f.read()

match = re.search(r'function renderHatchChart\(\) \{.*?(?=  function toggleFullScreenWrapper)', content, re.DOTALL)
if match:
    # Just print the datasets definition
    part = match.group(0)
    start = part.find('datasets: [')
    end = part.find('          },', start)
    print(part[start:end])
