import re

with open('templates/flock_charts.html', 'r') as f:
    content = f.read()

# remove old Plotly script blocks that might still be trailing
content = re.sub(r'<script>\s*// Initial Load\s*document.addEventListener\(\'DOMContentLoaded\', \(\) => \{\s*loadData\(\);\s*\}\);\s*</script>', '', content)
content = re.sub(r'<script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>', '', content)

with open('templates/flock_charts.html', 'w') as f:
    f.write(content)
