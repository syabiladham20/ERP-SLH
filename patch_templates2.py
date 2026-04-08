import re

def remove_extracted(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # Find the charts part
    start_charts = content.find('<!-- Charts Tab (Pane 3) -->')
    end_charts = content.find('<!-- Production Summary Tab (Pane 4) -->')
    content = content[:start_charts] + "<!-- Charts Tab included below -->\n" + content[end_charts:]

    # Find the modal part
    start_modal = content.find('<div class="modal fade" id="noteModal"')
    end_modal = content.find('<!-- Floating Note Modal -->')
    if start_modal != -1 and end_modal != -1:
        content = content[:start_modal] + content[end_modal:]

    with open(filepath, 'w') as f:
        f.write(content)

remove_extracted('templates/flock_detail.html')
remove_extracted('templates/flock_detail_modern.html')
remove_extracted('templates/flock_detail_readonly.html')
