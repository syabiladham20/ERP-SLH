import re

files_to_modify = [
    'templates/flock_detail.html',
    'templates/flock_detail_readonly.html',
    'templates/flock_detail_modern.html'
]

btn_html_template = '<button class="btn btn-sm btn-outline-secondary ms-1" onclick="toggleAddNoteMode(\'{chart_id}\')" title="Add Floating Note"><i class="bi bi-chat-square-text"></i></button>\n                '

# map targetCardId to actual chart instance ID used in JS
card_to_chart_map = {
    'cardGeneral': 'generalChart',
    'cardHatching': 'hatchingEggChart',
    'cardWater': 'waterChart',
    'cardFeed': 'feedChart',
    'cardMale': 'maleChart',
    'cardFemale': 'femaleChart',
    # read-only might have hatchChart?
    'cardHatch': 'hatchChart'
}

for filename in files_to_modify:
    with open(filename, 'r') as f:
        content = f.read()

    for card_id, chart_id in card_to_chart_map.items():
        pattern = r'(<button class="btn btn-sm[^"]*" onclick="toggleFullScreenWrapper\(\'' + card_id + r'\'\)")'

        btn_html = btn_html_template.format(chart_id=chart_id)

        # Check if already added
        if f"toggleAddNoteMode('{chart_id}')" not in content:
            # We want to insert the Add Note button BEFORE the Full Screen button
            content = re.sub(pattern, btn_html + r'\1', content)

    with open(filename, 'w') as f:
        f.write(content)

    print(f"Added buttons to {filename}")
