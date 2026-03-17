with open('templates/index.html', 'r') as f:
    content = f.read()

import re
# Remove the Cumulative Mortality block
content = re.sub(
    r'<div class="col-6 border-end">\s*<small class="text-muted">Rearing Mort %</small><br>\s*<strong>M: {{ "%\.2f"\|format\(flock\.rearing_mort_m_pct\) }}%</strong><br>\s*<strong>F: {{ "%\.2f"\|format\(flock\.rearing_mort_f_pct\) }}%</strong>\s*</div>',
    '',
    content
)
content = re.sub(
    r'<div class="col-4 border-end">\s*<small class="text-muted">Prod Mort %</small><br>\s*<strong>M: {{ "%\.2f"\|format\(flock\.prod_mort_m_pct\) }}%</strong><br>\s*<strong>F: {{ "%\.2f"\|format\(flock\.prod_mort_f_pct\) }}%</strong>\s*</div>',
    '',
    content
)

# Now adjust column widths since we removed a column
# Brooding/Growing phase: col-6 -> col-12 for the remaining Daily Mort / Male Ratio
content = content.replace(
    '''<div class="col-6">\n                            <small class="text-muted">Daily Mort %</small>''',
    '''<div class="col-12">\n                            <small class="text-muted">Daily Mort %</small>'''
)

# Production phase: col-4 -> col-6 for the remaining two columns
content = content.replace(
    '''<div class="col-4 border-end">\n                            <small class="text-muted">Daily Mort %</small>''',
    '''<div class="col-6 border-end">\n                            <small class="text-muted">Daily Mort %</small>'''
)
content = content.replace(
    '''<div class="col-4">\n                            <small class="text-muted">Egg Prod %</small>''',
    '''<div class="col-6">\n                            <small class="text-muted">Egg Prod %</small>'''
)

with open('templates/index.html', 'w') as f:
    f.write(content)
