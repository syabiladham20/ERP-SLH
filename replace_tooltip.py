import os
import glob

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # The interaction mode 'index' combined with intersect: false in hover might override events?
    # Let's completely remove hover interaction block and set interaction mode properly.
    if "events: ['click']," in content:
        # Update hover options
        content = content.replace("hover: {\n        mode: 'index',\n        intersect: false\n      },", "")
        # The plugins part is already updated. Let's see if interaction is overriding it
        # Actually in ChartJS 3/4, to disable tooltips on hover but keep them on click,
        # events: ['click'] is the right way at the top level of options.
        pass

for filepath in ["app/templates/flock_detail.html", "app/templates/flock_detail_modern.html", "app/templates/flock_detail_readonly.html"]:
    process_file(filepath)
