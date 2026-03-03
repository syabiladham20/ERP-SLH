import re

with open('templates/daily_log_form_responsive.html', 'r') as f:
    html = f.read()

# Instead of BS4, we use targeted Regex replacements for specific form blocks
# to ensure we don't break complex jinja layouts.

# General pattern for standard input field:
# <div class="col-12 col-md-6 mb-2">
#   <label class="form-label">Mortality Male (Prod)</label>
#   <input type="number" class="form-control" name="mortality_male" value="{{ log.mortality_male if log else 0 }}">
# </div>

# We want to transform to:
# <div class="col-12 col-md-6 mb-2">
#   <div class="form-floating">
#     <input type="number" class="form-control form-control-lg" name="mortality_male" id="mortality_male" placeholder="Mortality Male (Prod)" value="{{ log.mortality_male if log else 0 }}">
#     <label for="mortality_male">Mortality Male (Prod)</label>
#   </div>
# </div>

# Let's write a targeted function using re.sub with a replacement function

def replace_block(match):
    div_start = match.group(1) # <div class="col-12 col-md-6 mb-2">
    label_start = match.group(2) # <label class="form-label">
    label_text = match.group(3) # Mortality Male (Prod)
    label_end = match.group(4) # </label>
    input_tag = match.group(5) # <input type="number" class="form-control" name="mortality_male" value="{{ log.mortality_male if log else 0 }}">

    # We must not touch input groups, or inputs that already have an ID (which might be tied to JS logic)
    # Wait, we CAN touch inputs with IDs, we just need to reuse that ID for the label `for` attribute.

    # Extract name or ID from input
    id_match = re.search(r'id="([^"]+)"', input_tag)
    name_match = re.search(r'name="([^"]+)"', input_tag)

    input_id = id_match.group(1) if id_match else (name_match.group(1) if name_match else None)

    # If it's an array name (name="med_drug_name[]"), sanitize ID
    if input_id:
        input_id = input_id.replace('[]', '').replace('[', '').replace(']', '')

    # If no ID or Name, just generate a random one based on hash or index
    if not input_id:
        input_id = f"field_{abs(hash(label_text))}"

    # Ensure input tag has the ID
    if not id_match:
        input_tag = input_tag.replace('<input ', f'<input id="{input_id}" ')
        input_tag = input_tag.replace('<select ', f'<select id="{input_id}" ')
        input_tag = input_tag.replace('<textarea ', f'<textarea id="{input_id}" ')

    # Ensure input tag has placeholder
    if 'placeholder=' not in input_tag and ('<input' in input_tag or '<textarea' in input_tag):
        # Escape quotes in label text
        safe_label = label_text.replace('"', '&quot;')
        input_tag = input_tag.replace('<input ', f'<input placeholder="{safe_label}" ')
        input_tag = input_tag.replace('<textarea ', f'<textarea placeholder="{safe_label}" ')

    # Enlarge Inputs (User request)
    if 'form-control ' in input_tag or 'form-control"' in input_tag:
        if 'form-control-sm' not in input_tag and 'form-control-lg' not in input_tag:
            input_tag = input_tag.replace('form-control', 'form-control form-control-lg')

    if 'form-select ' in input_tag or 'form-select"' in input_tag:
        if 'form-select-sm' not in input_tag and 'form-select-lg' not in input_tag:
            input_tag = input_tag.replace('form-select', 'form-select form-select-lg')

    # Remove old class from label
    label_start_clean = label_start.replace('class="form-label"', '').replace('class="form-label small"', 'class="small"').replace('class="form-label text-muted small"', 'class="text-muted small"')

    # Inject "for" attribute
    if 'for=' not in label_start_clean:
        label_start_clean = label_start_clean.replace('<label', f'<label for="{input_id}"')

    # Construct floating label format
    return f"""{div_start}
  <div class="form-floating">
    {input_tag}
    {label_start_clean}{label_text}{label_end}
  </div>"""

# Match:
# <div class="..."> (1)
# \s*
# <label class="..."> (2)
# (text inside label) (3)
# </label> (4)
# \s*
# <input ...> or <select ...> or <textarea ...> (5)
# NOTE: Using re.DOTALL and non-greedy matching

pattern = re.compile(
    r'(<div[^>]*class="(?:col-|mb-|row)[^>]*>)\s*(<label[^>]*class="[^"]*form-label[^"]*"[^>]*>)(.*?)(</label>)\s*(<(?:input|select|textarea)[^>]*>)',
    re.DOTALL
)

new_html = pattern.sub(replace_block, html)

with open('templates/daily_log_form_floating.html', 'w') as f:
    f.write(new_html)
