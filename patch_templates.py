import re

def replace_in_template(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    start_charts = content.find('<!-- Charts Tab (Pane 3) -->')
    end_charts = content.find('<!-- Production Summary Tab (Pane 4) -->')

    start_modal = content.find('<div class="modal fade" id="noteModal"')
    end_modal = content.find('<!-- Floating Note Modal -->')

    start_scripts = content.find('<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>')
    end_scripts = content.find('{% endblock %}')

    # It's cleaner to just replace the scripts block first, then the modal, then the charts
    content = content[:start_scripts] + "{% include 'partials/_chart_module.html' %}\n" + content[end_scripts:]

    # We must be careful not to delete things out of order, or recalculate indexes.

    with open(filepath, 'w') as f:
        f.write(content)

replace_in_template('templates/flock_detail.html')
replace_in_template('templates/flock_detail_modern.html')
replace_in_template('templates/flock_detail_readonly.html')
