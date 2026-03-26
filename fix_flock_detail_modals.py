import re

for filename in ['templates/flock_detail.html', 'templates/flock_detail_modern.html', 'templates/flock_detail_readonly.html']:
    with open(filename, 'r') as f:
        content = f.read()

    note_modal_pattern = re.compile(r'(<!-- Note Modal -->.*?<div class="modal fade" id="noteModal".*?<div class="modal-dialog.*?<div class="modal-content">.*?<div class="modal-header">.*?</div>.*?<div class="modal-body">.*?</div>\s*</div>\s*</div>\s*</div>)', re.DOTALL)

    note_modal_match = note_modal_pattern.search(content)
    if note_modal_match:
        note_modal_str = note_modal_match.group(1)
        content = content.replace(note_modal_str, '')
    else:
        print(f"Failed to find Note Modal in {filename}")
        note_modal_str = ""

    chart_modal_pattern = re.compile(r'(<!-- Chart Fullscreen Modal -->.*?<div class="modal fade" id="chartFullscreenModal".*?<div class="modal-dialog.*?<div class="modal-content">.*?<div class="modal-header">.*?</div>.*?<div class="modal-body">.*?</div>\s*</div>\s*</div>\s*</div>)', re.DOTALL)
    chart_modal_match = chart_modal_pattern.search(content)
    if chart_modal_match:
        chart_modal_str = chart_modal_match.group(1)
        content = content.replace(chart_modal_str, '')
    else:
        print(f"Failed to find Chart Fullscreen Modal in {filename}")
        chart_modal_str = ""

    if note_modal_str or chart_modal_str:
        new_modals_block = "\n{% block modals %}\n" + note_modal_str + "\n" + chart_modal_str + "\n{% endblock %}\n"
        content = content + new_modals_block

        with open(filename, 'w') as f:
            f.write(content)
