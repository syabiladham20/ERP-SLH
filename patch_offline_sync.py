import re

with open('static/js/offline_sync.js', 'r') as f:
    content = f.read()

# Pattern 1:
content = re.sub(
    r'<<<<<<< HEAD\n    const ages = logs\.map\(l => l\.week_day_format \? String\(l\.week_day_format\)\.split\(\'\.\'\)\[0\] : \'N/A\'\);\n=======\n    const ages = logs\.map\(l => l\.age_week_day \? String\(l\.age_week_day\)\.split\(\'\.\'\)\[0\] : \'N/A\'\);\n>>>>>>> fix/color-contrast-orange-6176072627711246685',
    r'    const ages = logs.map(l => l.week_day_format ? String(l.week_day_format).split(\'.\')[0] : \'N/A\');',
    content
)

# Pattern 2:
content = re.sub(
    r'<<<<<<< HEAD\n                                <td>W\$\{l\.week_day_format \? String\(l\.week_day_format\)\.split\(\'\.\'\)\[0\] : \'N/A\'\}</td>\n=======\n                                <td>W\$\{l\.age_week_day \? String\(l\.age_week_day\)\.split\(\'\.\'\)\[0\] : \'N/A\'\}</td>\n>>>>>>> fix/color-contrast-orange-6176072627711246685',
    r'                                <td>W${l.week_day_format ? String(l.week_day_format).split(\'.\')[0] : \'N/A\'}</td>',
    content
)

with open('static/js/offline_sync.js', 'w') as f:
    f.write(content)
