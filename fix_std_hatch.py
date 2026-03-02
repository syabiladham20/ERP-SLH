import re

def add_std_hatch(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # Find hatchChart datasets
    # In hatchChart, there's already dStdHatch:
    # {
    #     label: 'Std Hatchability %',
    #     data: dStdHatch,
    #     type: 'line',
    #     borderColor: '#198754',
    #     borderDash: [5, 5],
    #     borderWidth: 2,
    #     pointRadius: 0,
    #     fill: false,
    #     order: 0,
    #     yAxisID: 'y1',
    #     clip: true
    # },
    # Let's see if this is in the file.

    match = re.search(r'label:\s*\'Std Hatchability %.*?(?=\{)', content, re.DOTALL)
    if match:
        print(f"Found Std Hatchability in {filepath}")

add_std_hatch('templates/flock_detail.html')
add_std_hatch('templates/flock_detail_readonly.html')
