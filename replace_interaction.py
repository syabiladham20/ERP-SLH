import glob

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # The issue might be that for tooltips to ONLY trigger on click in ChartJS 3+,
    # we specifically need to set events on the tooltip plugin, or set events at the root.
    # The events array determines which events the chart listens to.
    # But interaction mode might still listen to those events and trigger tooltips.

    # Wait, Chart.js tooltips have an `events` option inside `plugins.tooltip`?
    # No, the `events` option is at the top level of the chart configuration.
    # Wait, the `plugins.tooltip` has an `events` option in Chart.js 3+!
    # See documentation: "The events option can be used to control what events the tooltip responds to."
    # Let's add events: ['click'] directly to the tooltip plugin in commonOptions!

    # Wait, I previously did:
    # tooltip: { enabled: true }

    content = content.replace("tooltip: { enabled: true }", "tooltip: { enabled: true, events: ['click'] }")

    with open(filepath, 'w') as f:
        f.write(content)

for filepath in glob.glob("app/templates/flock_detail*.html"):
    process_file(filepath)
