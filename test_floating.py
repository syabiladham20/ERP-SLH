import re

with open('templates/daily_log_form_responsive.html', 'r') as f:
    html = f.read()

# Make sure we don't break the House select loop by closing the div too early.
# Wait, look at House:
# <div class="mb-3">
#   <div class="form-floating">
#     <select class="form-select form-select-lg" id="house_id" name="house_id" required onchange="onSelectionChange()">
#     <label for="house_id" >House</label>
#   </div>
#   {% for house in houses %} ...
# The select tag is NOT closed! It's matching only the opening tag `<select ...>`.
# This is because the regex only grabs the opening tag of `<select>` or `<textarea>`.

# So we cannot easily automate floating labels for complex inputs like select and textarea where content is inside!
# And even for input, `<div class="input-group">` breaks the standard floating label.
# To do this safely, we should modify the file directly or use a more precise Python parser.
# Given the user wants large inputs stacked, maybe we can just increase input sizes and ONLY wrap standard inputs.

# But `form-control-lg` + stacked columns (step 1 and 2) already fulfills the core requirement.
# Floating labels are a nice-to-have ("If Tabler supports it, use Floating Labels").
# Let's write a python script to manually update the most critical standard fields to floating labels.

def wrap_floating_labels(content):
    # Instead of regex magic, let's just make sure all form-control and form-select are -lg.
    # The user specifically said: "If Tabler supports it, use Floating Labels. It keeps the screen clean while making sure the user always knows what they are typing in."

    # We can do a string replacement for the most common block:
    # <div class="col-12 col-md-6 mb-2">
    #   <label class="form-label">Mortality Male (Prod)</label>
    #   <input type="number" class="form-control" name="mortality_male" value="{{ log.mortality_male if log else 0 }}">
    # </div>

    # Let's find all instances of label + input and replace them carefully.

    import re

    # Standard single-line inputs
    pattern = re.compile(r'(<div class="(?:col-12 col-md-[46]|col-4|col-6) mb-2">)\s*<label class="form-label">([^<]+)</label>\s*<input type="([^"]+)" (step="[^"]+" )?class="form-control" name="([^"]+)" (id="[^"]+" )?value="([^"]*)">\s*</div>', re.DOTALL)

    def replace_input(m):
        div_class = m.group(1)
        label_text = m.group(2)
        inp_type = m.group(3)
        inp_step = m.group(4) or ""
        inp_name = m.group(5)
        inp_id = m.group(6) or f'id="{inp_name}" '
        inp_val = m.group(7)

        return f"""{div_class}
            <div class="form-floating">
              <input type="{inp_type}" {inp_step}class="form-control form-control-lg" name="{inp_name}" {inp_id}placeholder="{label_text}" value="{inp_val}">
              <label for="{inp_name}">{label_text}</label>
            </div>
          </div>"""

    content = pattern.sub(replace_input, content)

    return content

with open('templates/daily_log_form_responsive.html', 'r') as f:
    html = f.read()

html = wrap_floating_labels(html)

with open('templates/daily_log_form_floating.html', 'w') as f:
    f.write(html)
