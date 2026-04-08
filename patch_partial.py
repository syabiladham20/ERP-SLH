import re

with open('templates/partials/_chart_module.html', 'r') as f:
    content = f.read()

# We need to wrap the `renderGeneralChart` inside an async fetch wrapper?
# The user instructed:
# "For the initial load, the script block should safely parse the injected Jinja data: let chartDataDaily = {{ chart_data | tojson | safe }};"
# "Keep the fetch('/api/chart_data/' + flockId) logic in the partial, but wrap it in a function (e.g., refreshChartData())"
# Wait, let's see how `chartDataDaily` is currently declared.

# In the current partial script block:
# const chartDataDaily = {{ chart_data | tojson }};
# const chartDataWeekly = {{ chart_data_weekly | tojson }};

# I need to change them to `let chartDataDaily` and `let chartDataWeekly` so they can be re-assigned.

content = content.replace("const chartDataDaily = {{ chart_data | tojson }};", "let chartDataDaily = {{ chart_data | tojson | safe }};")
content = content.replace("const chartDataWeekly = {{ chart_data_weekly | tojson }};", "let chartDataWeekly = {{ chart_data_weekly | tojson | safe }};")

# Also, I need to add `refreshChartData()` function.
refresh_func = """
  window.refreshChartData = function(flockId) {
      fetch('/api/chart_data/' + flockId)
          .then(response => response.json())
          .then(data => {
              chartDataDaily = data.daily;
              chartDataWeekly = data.weekly;

              if (currentMode === 'daily') {
                  renderGeneralChart();
                  renderHatchingEggChart();
                  renderWaterChart();
                  renderFeedChart();
                  renderMaleChart();
                  renderFemaleChart();
              } else {
                  renderGeneralChart();
                  renderHatchingEggChart();
                  renderMaleChart();
                  renderFemaleChart();
              }
          })
          .catch(err => console.error("Error refreshing chart data:", err));
  };
"""

script_tag_pos = content.find('<script>')
content = content[:script_tag_pos+8] + refresh_func + content[script_tag_pos+8:]

with open('templates/partials/_chart_module.html', 'w') as f:
    f.write(content)
