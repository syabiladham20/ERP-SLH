import re

def convert_to_floating(html_content):
    # Regex pattern to match standard label + input/select patterns
    # E.g.: <label class="form-label">Name</label> <input type="text" class="form-control" name="name" ...>
    # Note: floating labels structure is:
    # <div class="form-floating mb-3">
    #   <input type="..." class="form-control" id="..." placeholder="...">
    #   <label for="...">Name</label>
    # </div>

    # We will iterate through lines, parsing the HTML to restructure the elements into form-floating wrappers.
    # Because Regexing HTML is error-prone, a custom parser is safer.

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')

    # We look for typical patterns where label comes before an input/select
    # Instead of modifying the entire complex DOM automatically which might break scripts and specific layouts,
    # let's write a robust DOM replacement.

    # Actually, we can just replace the specific elements we know are safe.
    # The user specifically requested "If Tabler supports it, use Floating Labels. It keeps the screen clean".
    # Tabler and Bootstrap 5 both support form-floating.

    # Let's target `.mb-2`, `.mb-3` and `.col-*` divs that contain EXACTLY one label and one input/select

    targets = soup.find_all(lambda tag: tag.name == 'div' and tag.find('label') and (tag.find('input') or tag.find('select')))

    for div in targets:
        # Avoid input groups, file inputs, complex nested structures, or checkboxes
        if div.find(class_='input-group') or div.find(class_='form-check'):
            continue

        input_el = div.find(['input', 'select', 'textarea'])
        label_el = div.find('label')

        if not input_el or not label_el:
            continue

        # Avoid file inputs, checkboxes, radios
        if input_el.name == 'input' and input_el.get('type') in ['file', 'checkbox', 'radio', 'hidden']:
            continue

        # Ensure it's a direct child relationship or close enough
        # We wrap them in form-floating

        # Bootstrap floating labels require the input to be FIRST, then the label.
        # They also require an ID on the input, and the label to have `for="id"`.
        # They also require a `placeholder` attribute on the input (even if empty string) to trigger the CSS correctly.

        # Extract existing properties
        el_id = input_el.get('id')
        if not el_id:
            # Generate one based on name
            el_name = input_el.get('name')
            if el_name:
                # Remove brackets for array names
                clean_name = el_name.replace('[', '').replace(']', '')
                el_id = f"floating_{clean_name}_{id(input_el)}"
                input_el['id'] = el_id
            else:
                el_id = f"floating_{id(input_el)}"
                input_el['id'] = el_id

        label_el['for'] = el_id

        if input_el.name == 'input' and not input_el.get('placeholder'):
            input_el['placeholder'] = label_el.text.strip()

        # Add form-floating class to a new wrapper or the current div
        # If the div has col-* class, we shouldn't replace its classes entirely, just add form-floating.
        # However, form-floating handles margins differently sometimes.
        # To be safe, we wrap the input and label in a new <div class="form-floating">

        floating_div = soup.new_tag('div', attrs={'class': 'form-floating w-100'})

        # Move classes that make sense? No, keep the grid classes on the parent div.
        # Just insert the floating div inside the parent, and move the input+label inside it.

        # Re-order: Input first, then label

        input_el.extract()
        label_el.extract()

        # Remove old form-label class as floating labels use standard labels
        if 'form-label' in label_el.get('class', []):
            label_el['class'].remove('form-label')

        # Enlarge inputs per previous requirement
        if 'form-control' in input_el.get('class', []):
            if 'form-control-sm' not in input_el.get('class', []):
                if 'form-control-lg' not in input_el.get('class', []):
                    input_el['class'].append('form-control-lg')

        if 'form-select' in input_el.get('class', []):
            if 'form-select-sm' not in input_el.get('class', []):
                if 'form-select-lg' not in input_el.get('class', []):
                    input_el['class'].append('form-select-lg')

        floating_div.append(input_el)
        floating_div.append(label_el)

        # Append floating_div to the original container
        # Since we extracted the original ones, the container might be empty or have other text.
        # We append it to the start of the div
        div.insert(0, floating_div)

    return str(soup)

with open('templates/daily_log_form_responsive.html', 'r') as f:
    html = f.read()

# Before running beautifulsoup, which sometimes messes up jinja templating tags,
# We should probably do a targeted string replacement or be very careful.
# Jinja tags inside attribute values (like value="{{...}}") are preserved by bs4 usually.
# But {% if ... %} blocks around elements might get tangled.

# Let's test the bs4 conversion on a small string first.
