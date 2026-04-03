import re

with open('templates/hatchability_diagnosis.html', 'r') as f:
    content = f.read()

content = re.sub(
    r'<<<<<<< HEAD\n                                <td>{{ log\.age_week_format }} W</td>\n=======\n                                <td>{{ log\.age_week_day }} W</td>\n>>>>>>> fix/color-contrast-orange-6176072627711246685',
    r'                                <td>{{ log.age_week_format }} W</td>',
    content
)

with open('templates/hatchability_diagnosis.html', 'w') as f:
    f.write(content)


with open('templates/post_mortem.html', 'r') as f:
    content = f.read()

content = re.sub(
    r'<<<<<<< HEAD\n                                    <td>{{ log\.age_week_format }}</td>\n=======\n                                    <td>{{ log\.age_week_day }}</td>\n>>>>>>> fix/color-contrast-orange-6176072627711246685',
    r'                                    <td>{{ log.age_week_format }}</td>',
    content
)

with open('templates/post_mortem.html', 'w') as f:
    f.write(content)
