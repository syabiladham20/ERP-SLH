import re

with open('templates/daily_log_form.html', 'r') as f:
    content = f.read()

# Make columns responsive (mobile first, side-by-side on desktop)
# We only target classes starting with col-6, col-4, col-3.
content = re.sub(r'class="col-6([^"]*)"', r'class="col-12 col-md-6\1"', content)
content = re.sub(r'class="col-4([^"]*)"', r'class="col-12 col-md-4\1"', content)
content = re.sub(r'class="col-3([^"]*)"', r'class="col-12 col-md-3\1"', content)

# Check for instances of col-md-4 that might have been accidentally prefixed with col-12 col-md- (not needed if regex looks for ^col- or spacing)
# Our regex targets `class="col-X ` so `col-md-X` is unaffected.

with open('templates/daily_log_form.html', 'w') as f:
    f.write(content)
