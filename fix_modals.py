import os
import re

for root, _, files in os.walk('templates'):
    for file in files:
        if file.endswith('.html'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r') as f:
                content = f.read()

            def replace_modal(match):
                raw_classes = match.group(1)

                # Split by whitespace to get individual classes, filter out empty ones
                classes_list = [c for c in raw_classes.split() if c.strip()]

                if 'modal-dialog-centered' in classes_list:
                    classes_list.remove('modal-dialog-centered')

                if 'modal-dialog-scrollable' not in classes_list:
                    classes_list.append('modal-dialog-scrollable')

                has_fullscreen = any(c.startswith('modal-fullscreen') for c in classes_list)
                if not has_fullscreen:
                    classes_list.append('modal-fullscreen-sm-down')

                final_classes = ' '.join(classes_list)
                if final_classes:
                    return f'class="modal-dialog {final_classes}"'
                return 'class="modal-dialog"'

            # Replace 'class="modal-dialog ..."'
            content = re.sub(r'class="modal-dialog\s*([^"]*)"', replace_modal, content)

            # Special case for 'class="modal-dialog"'
            content = re.sub(r'class="modal-dialog"', 'class="modal-dialog modal-dialog-scrollable modal-fullscreen-sm-down"', content)

            # Cleanup potential duplicate definitions if the regex matched multiple times
            content = re.sub(r'class="modal-dialog modal-dialog-scrollable modal-fullscreen-sm-down modal-dialog-scrollable modal-fullscreen-sm-down"', 'class="modal-dialog modal-dialog-scrollable modal-fullscreen-sm-down"', content)

            with open(filepath, 'w') as f:
                f.write(content)
