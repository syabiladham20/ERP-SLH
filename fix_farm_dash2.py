with open('templates/index.html', 'r') as f:
    content = f.read()
import re
# Now we remove the Hatchery blocks completely
content = re.sub(
    r'{%\s*if flock\.latest_hatch\s*%}.*?{%\s*endif\s*%}',
    '',
    content,
    flags=re.DOTALL
)
with open('templates/index.html', 'w') as f:
    f.write(content)
