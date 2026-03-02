import re

with open('templates/flock_detail.html', 'r') as f:
    content = f.read()

bad_plugins = """              plugins: {
                  legend: commonOptions.plugins.legend,
                  zoom: commonOptions.plugins.zoom,
                                    datalabels: {
                       display: function(context) { return context.chart.options.plugins.datalabels.display; },
                       formatter: function(value, context) { if (!value) return ''; return parseFloat(value).toFixed(2) + '%'; }
                  },
                  tooltip: commonOptions.plugins.tooltip
              }"""

good_plugins = """              plugins: {
                  ...commonOptions.plugins
              }"""

content = content.replace(bad_plugins, good_plugins)

with open('templates/flock_detail.html', 'w') as f:
    f.write(content)
