import re

with open('templates/daily_log_form_responsive.html', 'r') as f:
    html = f.read()

# The regex swallowed too much (from Date to Mortality Male). We must be more precise.
# We'll match only the immediate tags:
# <div class="..."> (1)
# \s*
# <label class="form-label" ...>Text</label> (2,3,4)
# \s*
# <input ...> or <select ...> or <textarea ...> (5)
# Ensure there are no other tags between them!

pattern = re.compile(
    r'(<div[^>]*class="[^"]*(?:col-|mb-|row)[^"]*"[^>]*>)\s*(<label[^>]*class="[^"]*form-label[^"]*"[^>]*>)([^<]*)(</label>)\s*(<(?:input|select|textarea)[^>]*>)',
    re.DOTALL
)

def replace_block(match):
    div_start = match.group(1)
    label_start = match.group(2)
    label_text = match.group(3).strip()
    label_end = match.group(4)
    input_tag = match.group(5)

    # Ignore hidden inputs or non-standard ones
    if 'type="hidden"' in input_tag or 'type="file"' in input_tag or 'type="checkbox"' in input_tag:
        return match.group(0) # Do not modify

    id_match = re.search(r'id="([^"]+)"', input_tag)
    name_match = re.search(r'name="([^"]+)"', input_tag)

    input_id = id_match.group(1) if id_match else (name_match.group(1) if name_match else None)

    if input_id:
        input_id = input_id.replace('[]', '').replace('[', '').replace(']', '')

    if not input_id:
        input_id = f"field_{abs(hash(label_text))}"

    if not id_match:
        input_tag = input_tag.replace('<input ', f'<input id="{input_id}" ')
        input_tag = input_tag.replace('<select ', f'<select id="{input_id}" ')
        input_tag = input_tag.replace('<textarea ', f'<textarea id="{input_id}" ')

    if 'placeholder=' not in input_tag and ('<input' in input_tag or '<textarea' in input_tag):
        safe_label = label_text.replace('"', '&quot;')
        input_tag = input_tag.replace('<input ', f'<input placeholder="{safe_label}" ')
        input_tag = input_tag.replace('<textarea ', f'<textarea placeholder="{safe_label}" ')

    if 'form-control' in input_tag and 'form-control-lg' not in input_tag and 'form-control-sm' not in input_tag:
        input_tag = input_tag.replace('form-control', 'form-control form-control-lg')

    if 'form-select' in input_tag and 'form-select-lg' not in input_tag and 'form-select-sm' not in input_tag:
        input_tag = input_tag.replace('form-select', 'form-select form-select-lg')

    # Remove old class from label
    label_start_clean = re.sub(r'class="[^"]*form-label[^"]*"', '', label_start)
    if 'for=' not in label_start_clean:
        label_start_clean = label_start_clean.replace('<label', f'<label for="{input_id}"')

    return f"""{div_start}
  <div class="form-floating">
    {input_tag}
    {label_start_clean}{label_text}{label_end}
  </div>"""

new_html = pattern.sub(replace_block, html)

with open('templates/daily_log_form_floating.html', 'w') as f:
    f.write(new_html)
