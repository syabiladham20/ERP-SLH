import re

with open('templates/flock_detail.html', 'r') as f:
    content = f.read()

start_idx = content.find('const commonOptions =')
end_idx = content.find('  };', start_idx) + 4
print(content[start_idx:end_idx])
