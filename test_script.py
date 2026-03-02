import re

file_path = "templates/hatchery_charts.html"
with open(file_path, "r") as f:
    content = f.read()

# Update getOptions logic (since the prompt said "include hatchery if applicable" for the dynamic max ranges)
new_getOptions = """function getOptions(values, isPercentage) {
        return {
            beginAtZero: true,
            grace: isPercentage ? '5%' : '25%'
        };
    }"""
content = re.sub(r'function getOptions\([^)]+\) \{[\s\S]*?return \{min: 0, suggestedMax: limit\};\n    \}', new_getOptions, content)

# Update zoom limits
new_zoom = """                    zoom: {
                        limits: {
                            x: {min: 'original', max: 'original'},
                            y: {min: 'original', max: 'original'},
                            y1: {min: 'original', max: 'original'}
                        },
                        zoom: {"""
content = re.sub(r'                    zoom: \{\n                        zoom: \{', new_zoom, content)


with open(file_path, "w") as f:
    f.write(content)
