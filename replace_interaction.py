import glob

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # The user says "now i see the tooltip on click but cant hide it back"
    # To hide the tooltip on Chart.js when events are restricted to ['click'], clicking somewhere else
    # doesn't always hide it if the click doesn't trigger the tooltip plugin's logic or if the chart itself
    # isn't catching the click outside the elements.

    # Actually, adding 'mouseout' or 'click' outside might be needed.
    # The default events are ['mousemove', 'mouseout', 'click', 'touchstart', 'touchmove']
    # If we want to hide it, we might need to add a custom onClick handler to hide tooltips, or
    # just use events: ['click', 'touchstart'] ? No, 'click' alone doesn't dismiss if you click on the canvas background.

    # Wait, Chart.js by default dismisses tooltips when you click on the chart background IF the interaction mode allows it.

    # Let's write a small script to attach a generic click listener to the document to hide all tooltips
    # by getting the active chart instance and calling chart.tooltip.setActiveElements([], {x:0, y:0}) or chart.update().

    # Actually, a much cleaner Chart.js way to handle toggle tooltips on click without hover:
    # 1. We keep events: ['click']
    # 2. In commonOptions or specifically for charts, if we click outside a data point, Chart.js automatically clears the active elements
    #    UNLESS `interaction.mode: 'index'` and `intersect: false` is making it grab the nearest point anyway!

    # Yes! `interaction: { mode: 'index', intersect: false }` means that EVEN IF you click on empty space,
    # it finds the nearest point and shows the tooltip for it.
    # So you CANNOT click on empty space to hide it because it will just select the nearest point!

    # If we change `intersect: false` to `intersect: true`, then clicking on empty space will HIDE the tooltip.

    content = content.replace("interaction: { mode: 'index', intersect: false },", "interaction: { mode: 'index', intersect: true },")
    content = content.replace("interaction: {\n        mode: 'index',\n        intersect: false,\n      },", "interaction: {\n        mode: 'index',\n        intersect: true,\n      },")

    with open(filepath, 'w') as f:
        f.write(content)

for filepath in glob.glob("app/templates/flock_detail*.html"):
    process_file(filepath)
