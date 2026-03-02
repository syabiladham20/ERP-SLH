import re

with open('templates/flock_detail_readonly.html', 'r') as f:
    content = f.read()

# Replace tooltip override in waterChart
old_plugins = """              plugins: {
                  ...commonOptions.plugins,
                  tooltip: {
                      callbacks: {
                          afterBody: function(context) {
                              const idx = context[0].dataIndex;
                              if (flushFlags[idx]) {
                                  return "FLUSHING ACTIVE";
                              }
                          }
                      }
                  }
              }"""

new_plugins = """              plugins: {
                  ...commonOptions.plugins,
                  tooltip: {
                      ...commonOptions.plugins.tooltip,
                      callbacks: {
                          ...commonOptions.plugins.tooltip.callbacks,
                          afterBody: function(context) {
                              const idx = context[0].dataIndex;
                              if (flushFlags && flushFlags[idx]) {
                                  return "FLUSHING ACTIVE";
                              }
                              return commonOptions.plugins.tooltip.callbacks.afterBody ? commonOptions.plugins.tooltip.callbacks.afterBody(context) : '';
                          }
                      }
                  }
              }"""

content = content.replace(old_plugins, new_plugins)

with open('templates/flock_detail_readonly.html', 'w') as f:
    f.write(content)
