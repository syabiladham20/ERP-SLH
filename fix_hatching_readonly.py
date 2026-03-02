import re

with open('templates/flock_detail_readonly.html', 'r') as f:
    content = f.read()

# Fix the override of datalabels inside hatchingEggChart
bad_plugins = """              plugins: {
                  ...commonOptions.plugins,
                  weekSeparator: { enabled: mode === 'daily' },
                                    datalabels: {
                       display: function(context) { return context.chart.options.plugins.datalabels.display; },
                       formatter: function(value, context) { if (!value) return ''; return parseFloat(value).toFixed(2) + '%'; }
                  },
                  tooltip: commonOptions.plugins.tooltip
              },"""

good_plugins = """              plugins: {
                  ...commonOptions.plugins,
                  weekSeparator: { enabled: mode === 'daily' }
              },"""

content = content.replace(bad_plugins, good_plugins)

with open('templates/flock_detail_readonly.html', 'w') as f:
    f.write(content)
