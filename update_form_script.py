import re

with open('templates/daily_log_form.html', 'r') as f:
    content = f.read()

# Make columns responsive (mobile first, side-by-side on desktop)
content = re.sub(r'class="col-6([^"]*)"', r'class="col-12 col-md-6\1"', content)
content = re.sub(r'class="col-4([^"]*)"', r'class="col-12 col-md-4\1"', content)
content = re.sub(r'class="col-3([^"]*)"', r'class="col-12 col-md-3\1"', content)

# Make sure existing col-md-* are preserved if they are already there
# (The above regex might not catch things properly if it's already col-md-4)
# Let's run a check first

with open('templates/daily_log_form_responsive.html', 'w') as f:
    f.write(content)
