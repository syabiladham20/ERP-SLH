import re

def fix_chart_options(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # The issue:
    # In `waterChart`, we do:
    # plugins: { ...commonOptions.plugins, tooltip: { callbacks: { ... } } }
    # This shallow-copies commonOptions.plugins, but then overrides `tooltip`.
    # Wait, it OVERWRITES `tooltip` entirely!
    # `commonOptions.plugins.tooltip.callbacks.label` is lost!
    # And more importantly, `commonOptions.plugins.datalabels` is preserved? Yes, because it's not overridden.
    # What about `zoom`? Preserved.

    # Let's fix tooltips by deeply merging or copying what we need:
    # Actually, Chart.js can merge if we structure it right, but `...` spread syntax is standard JS, not Chart.js merge.
    # Chart.js does its own deep merge when parsing the object!
    # But wait, `...commonOptions.plugins` passes an object. Then `tooltip: { ... }` REPLACES the `tooltip` property in that object.
    # So `commonOptions.plugins.tooltip` is gone.

    # We should merge tooltips explicitly:
    # tooltip: {
    #     ...commonOptions.plugins.tooltip,
    #     callbacks: {
    #         ...commonOptions.plugins.tooltip.callbacks,
    #         afterBody: function(context) { ... }
    #     }
    # }

    # Let's check where `...commonOptions.plugins` is used.
    print(f"Checking {filepath} for ...commonOptions.plugins")
    matches = re.finditer(r'plugins:\s*\{\s*\.\.\.commonOptions\.plugins,([^}]*)\}', content)
    for m in matches:
        print(m.group(0))

fix_chart_options('templates/flock_detail.html')
