import re

files_to_patch = [
    'templates/index.html',
    'templates/index_modern.html',
    'templates/executive_dashboard.html',
    'templates/executive_dashboard_modern.html',
    'templates/flock_detail_modern.html',
    'templates/flock_detail_readonly.html'
]

badge_pattern_html = "badge {% if flock.calculated_phase == 'Brooding' %}bg-primary{% elif flock.calculated_phase == 'Growing' %}bg-info{% elif flock.calculated_phase == 'Pre-lay' %}bg-warning{% else %}bg-success{% endif %}"
border_pattern_html = "border-3 {% if flock.calculated_phase == 'Brooding' %}border-primary{% elif flock.calculated_phase == 'Growing' %}border-info{% elif flock.calculated_phase == 'Pre-lay' %}border-warning{% else %}border-success{% endif %}"
badge_pattern_lt = "badge {% if flock.calculated_phase == 'Brooding' %}bg-primary-lt{% elif flock.calculated_phase == 'Growing' %}bg-info-lt{% elif flock.calculated_phase == 'Pre-lay' %}bg-warning-lt{% else %}bg-success-lt{% endif %}"


for fpath in files_to_patch:
    with open(fpath, 'r') as f:
        content = f.read()

    # JS 'Rearing' checks
    content = content.replace("const isRearing = (flockPhase === 'Rearing');", "const isRearing = (flockPhase === 'Brooding' || flockPhase === 'Growing');")

    # Text 'Rearing Mort %' checks
    content = content.replace("Rearing Mort %", "Brooding/Growing Mort %")

    # Phase print text
    content = content.replace('{{ flock.phase }}', '{{ flock.calculated_phase }}')

    # CSS badges (if any still use old syntax)
    content = re.sub(r'badge bg-\{\{ \'primary\' if flock\.calculated_phase == \'Rearing\' else \'warning\' \}\}', badge_pattern_html, content)
    content = re.sub(r'badge bg-\{\{ \'primary\' if flock\.calculated_phase == \'Rearing\' else \'success\' \}\}', badge_pattern_html, content)
    content = re.sub(r'badge bg-\{\{ \'success\' if flock\.calculated_phase == \'Production\' else \'primary\' \}\}', badge_pattern_html, content)
    content = re.sub(r'border-3 \{% if flock\.calculated_phase == \'Production\' %\}border-success\{% else %\}border-primary\{% endif %\}', border_pattern_html, content)

    content = re.sub(r'badge \{% if flock\.calculated_phase == \'Production\' %\}bg-success-lt\{% else %\}bg-primary-lt\{% endif %\}', badge_pattern_lt, content)
    content = re.sub(r'border-3 \{% if flock\.calculated_phase == \'Production\' %\}border-success\{% else %\}border-primary\{% endif %\}', border_pattern_html, content)

    # Some templates might not have been caught in previous loops
    content = content.replace("{% if flock.calculated_phase == 'Rearing' %}", "{% if flock.calculated_phase in ['Brooding', 'Growing'] %}")
    content = content.replace("{% if flock.calculated_phase != 'Rearing' %}", "{% if flock.calculated_phase in ['Pre-lay', 'Production'] %}")
    content = content.replace("{% if flock.calculated_phase == 'Rearing' %}Production{% else %}Rearing{% endif %}", "{% if flock.calculated_phase in ['Brooding', 'Growing'] %}Production{% else %}Rearing{% endif %}")

    with open(fpath, 'w') as f:
        f.write(content)
