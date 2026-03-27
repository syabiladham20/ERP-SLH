import os
import re
import glob

def move_modals(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # Simple regex stack-based approach
    modals = []
    lines = content.split('\n')

    new_lines = []
    in_modal = False
    modal_lines = []
    div_count = 0

    for line in lines:
        if not in_modal:
            # check if line starts a modal
            # Some lines might have both start and end, we assume standard indentation format
            if re.search(r'<div[^>]*class="[^"]*\bmodal\b[^"]*"', line):
                in_modal = True
                modal_lines = [line]
                div_count = line.count('<div') - line.count('</div')
            else:
                new_lines.append(line)
        else:
            modal_lines.append(line)
            div_count += line.count('<div') - line.count('</div')
            if div_count == 0:
                in_modal = False
                modals.append('\n'.join(modal_lines))
                modal_lines = []

    if not modals:
        return

    final_content = '\n'.join(new_lines)

    if '{% endblock %}' in final_content:
        parts = final_content.rsplit('{% endblock %}', 1)
        final_content = parts[0] + '\n\n<!-- Moved Modals -->\n' + '\n\n'.join(modals) + '\n{% endblock %}' + parts[1]
    elif '</body>' in final_content:
        parts = final_content.rsplit('</body>', 1)
        final_content = parts[0] + '\n\n<!-- Moved Modals -->\n' + '\n\n'.join(modals) + '\n</body>' + parts[1]
    else:
        final_content += '\n\n<!-- Moved Modals -->\n' + '\n\n'.join(modals)

    with open(filepath, 'w') as f:
        f.write(final_content)

    print(f"Moved {len(modals)} modals in {filepath}")

for file in glob.glob('templates/**/*.html', recursive=True):
    with open(file, 'r') as f:
        if '<div class="modal' in f.read():
            move_modals(file)
