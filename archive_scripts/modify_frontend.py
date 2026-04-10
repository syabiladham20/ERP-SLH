import re

files_to_modify = [
    'templates/flock_detail.html',
    'templates/flock_detail_readonly.html',
    'templates/flock_detail_modern.html'
]

script_tag = '<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@2.1.0/dist/chartjs-plugin-annotation.min.js"></script>'

for filename in files_to_modify:
    try:
        with open(filename, 'r') as f:
            content = f.read()

        # 1. Add script tag
        if "chartjs-plugin-annotation" not in content:
            content = re.sub(
                r'(<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@.*?></script>)',
                r'\1\n' + script_tag,
                content
            )

        # 2. Add plugin registration
        if "Chart.register(ChartDataLabels);" in content and "chartjsPluginAnnotation" not in content:
            content = content.replace(
                "Chart.register(ChartDataLabels);",
                "Chart.register(ChartDataLabels);\n  Chart.register(window['chartjs-plugin-annotation']);"
            )

        with open(filename, 'w') as f:
            f.write(content)

        print(f"Modified {filename}")
    except Exception as e:
        print(f"Error modifying {filename}: {e}")
