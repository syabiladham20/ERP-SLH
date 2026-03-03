import re

def expand_inputs(content):
    # As requested: form-control -> form-control-lg, form-select -> form-select-lg
    content = content.replace('class="form-control"', 'class="form-control form-control-lg"')
    content = content.replace('class="form-select"', 'class="form-select form-select-lg"')
    return content

with open('templates/daily_log_form_floating.html', 'r') as f:
    html = f.read()

# Apply the input enlargements as well (from step 2)
html = expand_inputs(html)

with open('templates/daily_log_form_final.html', 'w') as f:
    f.write(html)
