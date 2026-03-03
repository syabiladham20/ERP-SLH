import re

with open('templates/daily_log_form.html', 'r') as f:
    content = f.read()

# Make form controls larger
# For floating labels, Bootstrap 5 handles sizing differently, but since step 3 adds floating labels,
# let's modify the form to use floating labels, which will implicitly enlarge the input areas.
# However, if we just want to add form-control-lg and form-select-lg for touch targets:
# Be careful not to replace form-control-sm if it's explicitly used in compact tables.

content = re.sub(r'class="form-control"', r'class="form-control form-control-lg"', content)
content = re.sub(r'class="form-select"', r'class="form-select form-select-lg"', content)

# But wait, step 3 is implementing floating labels. Floating labels in Bootstrap 5 already provide a taller, finger-friendly input target by default because they contain both label and input within a single block.
# Let's combine these steps.

with open('templates/daily_log_form_large.html', 'w') as f:
    f.write(content)
