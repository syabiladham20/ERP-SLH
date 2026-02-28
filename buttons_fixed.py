import re

for filename in ['templates/flock_detail.html', 'templates/flock_detail_readonly.html']:
    with open(filename, 'r') as f:
        content = f.read()

    # Replace the incorrectly indented and unspaced button
    content = re.sub(
        r'                </div>\s+<button class="btn btn-sm btn-outline-secondary me-1" onclick="toggleDataLabels\(([^)]+)\)" title="Toggle Data Labels">\s+Labels\s+</button>',
        r'                </div>\n                <button class="btn btn-sm btn-outline-secondary ms-2" onclick="toggleDataLabels(\1)" title="Toggle Data Labels">Labels</button>',
        content
    )

    with open(filename, 'w') as f:
        f.write(content)
