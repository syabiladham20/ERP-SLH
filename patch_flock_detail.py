import re

files = [
    'templates/flock_detail.html',
    'templates/flock_detail_modern.html',
    'templates/flock_detail_readonly.html'
]

for filepath in files:
    with open(filepath, 'r') as f:
        content = f.read()

    content = re.sub(
        r'<<<<<<< HEAD\n            <td>W{{ item\.log\.age_week }}</td>\n=======\n            <td>W{{ item\.log\.age_week_day\.split\(\'\.\'\)\[0\] }}</td>\n>>>>>>> fix/color-contrast-orange-6176072627711246685',
        r'            <td>W{{ item.log.age_week }}</td>',
        content
    )

    with open(filepath, 'w') as f:
        f.write(content)
