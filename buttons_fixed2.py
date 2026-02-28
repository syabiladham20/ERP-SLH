import re

for filename in ['templates/flock_detail.html', 'templates/flock_detail_readonly.html']:
    with open(filename, 'r') as f:
        content = f.read()

    # Let's check how the full screen button is placed and put them side by side.
    # We want them in a group or just space them out properly
    # Currently they are like:
    # <button class="btn btn-sm btn-outline-secondary ms-2" onclick="toggleDataLabels('generalChart', this)" title="Toggle Data Labels">Labels</button>
    # <button class="btn btn-sm btn-outline-secondary" onclick="toggleFullScreenWrapper('cardGeneral')" title="Full Screen">

    content = re.sub(
        r'<button class="btn btn-sm btn-outline-secondary ms-2" (onclick="toggleDataLabels[^>]+>Labels</button>)\s+<button class="btn btn-sm btn-outline-secondary"',
        r'<button class="btn btn-sm btn-outline-secondary ms-2" \1\n                <button class="btn btn-sm btn-outline-secondary ms-1"',
        content
    )

    with open(filename, 'w') as f:
        f.write(content)
