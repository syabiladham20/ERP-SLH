import re

def insert_buttons(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    charts = [
        ('generalChart', 'cardGeneral'),
        ('hatchingEggChart', 'cardHatching'),
        ('waterChart', 'cardWater'),
        ('feedChart', 'cardFeed'),
        ('maleChart', 'cardMale'),
        ('femaleChart', 'cardFemale'),
        ('hatchChart', 'cardHatch')
    ]

    for chart_id, card_id in charts:
        button_html = f"""                <button class="btn btn-sm btn-outline-secondary" onclick="toggleDataLabels('{chart_id}', this)" title="Toggle Data Labels">
                    <i class="bi bi-tag"></i>
                </button>
                <button class="btn btn-sm btn-outline-secondary" onclick="resetZoom({chart_id})" title="Reset Zoom">"""

        # In case the regex replacement previously failed due to exact matching
        content = re.sub(
            fr'<button class="btn btn-sm btn-outline-secondary" onclick="resetZoom\({chart_id}\)" title="Reset Zoom">',
            button_html,
            content
        )

    with open(filepath, 'w') as f:
        f.write(content)

insert_buttons('templates/flock_detail.html')
insert_buttons('templates/flock_detail_readonly.html')
