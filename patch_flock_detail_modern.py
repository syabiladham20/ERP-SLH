import re

files = ['templates/flock_detail_modern.html', 'templates/flock_detail_readonly.html']

search_str = """              scales: {
                  y: {
                      type: 'linear',
                      display: true,
                      position: 'left',
                      title: { display: true, text: 'Water (ml)' },
                      ...scales
                  }
              },"""

replace_str = """              scales: {
                  y: {
                      type: 'linear',
                      display: true,
                      position: 'left',
                      title: { display: true, text: 'Water (ml)' },
                      ...scales
                  },
                  y1: {
                      type: 'linear',
                      display: true,
                      position: 'right',
                      title: { display: true, text: 'Ratio' },
                      grid: { drawOnChartArea: false }
                  }
              },"""

for file_name in files:
    with open(file_name, 'r') as f:
        content = f.read()

    if search_str in content:
        content = content.replace(search_str, replace_str)
        with open(file_name, 'w') as f:
            f.write(content)
        print(f"{file_name} patched successfully!")
    else:
        print(f"Could not find search_str in {file_name}")
