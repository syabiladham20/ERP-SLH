import re

with open('templates/flock_detail.html', 'r') as f:
    content = f.read()

match = re.search(r'function toggleDataLabels\([^)]*\)\s*\{.*?(?=function|\</script\>)', content, re.DOTALL)
if match:
    print(match.group(0))
