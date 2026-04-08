import re

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # Find the data definitions
    chart_data_start = content.find('const chartDataDaily =')
    if chart_data_start == -1:
        return

    # find renderGeneralChart function to see what data it expects
    general_chart_start = content.find('function renderGeneralChart')
    general_chart_end = content.find('}', content.find('}', general_chart_start)+1)

    print(f"File {filepath} has rendering logic")

process_file('templates/flock_detail.html')
process_file('templates/flock_detail_modern.html')
process_file('templates/flock_detail_readonly.html')
