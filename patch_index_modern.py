import re

with open('templates/index_modern.html', 'r') as f:
    content = f.read()

content = re.sub(
    r'<<<<<<< HEAD\n                                    backgroundColor: \'lightblue\',\n=======\n                                    backgroundColor: \'#520808\',\n>>>>>>> fix/color-contrast-orange-6176072627711246685',
    r'                                    backgroundColor: \'#520808\',',
    content
)

content = re.sub(
    r'<<<<<<< HEAD\n                                    datalabels: { align: \'top\', anchor: \'end\', color: \'lightblue\', backgroundColor: \'rgba\(255, 255, 255, 0\.7\)\', borderRadius: 3, padding: 2, font: {size: 10}, formatter: v => v > 0 \? v\.toFixed\(2\) : \'\' }\n=======\n                                    datalabels: { align: \'top\', anchor: \'end\', color: \'#520808\', backgroundColor: \'rgba\(255, 255, 255, 0\.7\)\', borderRadius: 3, padding: 2, font: {size: 10}, formatter: v => v > 0 \? v\.toFixed\(2\) : \'\' }\n>>>>>>> fix/color-contrast-orange-6176072627711246685',
    r'                                    datalabels: { align: \'top\', anchor: \'end\', color: \'#520808\', backgroundColor: \'rgba(255, 255, 255, 0.7)\', borderRadius: 3, padding: 2, font: {size: 10}, formatter: v => v > 0 ? v.toFixed(2) : \'\' }',
    content
)

with open('templates/index_modern.html', 'w') as f:
    f.write(content)
