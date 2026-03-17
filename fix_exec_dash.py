with open('templates/executive_dashboard.html', 'r') as f:
    content = f.read()

import re
# Remove the two inventory blocks: Low Stock Alerts and Available Stock
content = re.sub(
    r'{%\s*if low_stock_count > 0\s*%}.*?{%\s*endif\s*%}',
    '',
    content,
    flags=re.DOTALL
)

# Available stock block might not be wrapped in an if block, let's find it.
start = content.find('<div class="card border-success mb-4">')
if start != -1:
    end = content.find('</div>\n      </div>\n\n      <div class="row">', start)
    if end != -1:
        content = content[:start] + content[end + 13:] # +13 to remove the closing tags of the card

with open('templates/executive_dashboard.html', 'w') as f:
    f.write(content)
