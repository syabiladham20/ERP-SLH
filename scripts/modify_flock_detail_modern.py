import re

with open('templates/flock_detail_modern.html', 'r') as f:
    content = f.read()

# We need to nuke the old chart rendering functions and replace them with the simplified fetch based ones.
content = content.replace("const chartDataDaily = {{ chart_data | tojson }};", "")
content = content.replace("const chartDataWeekly = {{ chart_data_weekly | tojson }};", "")

def create_chart_initializer():
    return """
  // Single SSOT render function!
  function initOrUpdateChart(chartVar, canvasId, chartDataGroup) {
      const canvas = document.getElementById(canvasId);
      if (!canvas) return chartVar; // Guard for views missing a specific chart
      const ctx = canvas.getContext('2d');
      if (chartVar) {
          chartVar.data = chartDataGroup;
          chartVar.update();
          return chartVar;
      }

      return new Chart(ctx, {
          data: chartDataGroup,
          options: {
              responsive: true,
              maintainAspectRatio: false,
              interaction: { mode: 'index', intersect: false },
              plugins: {
                  legend: { position: 'bottom' },
                  dynamicYMaxPlugin: true
              },
              onClick: function(e, elements) {
                  if (elements.length > 0) {
                      const idx = elements[0].index;
                      const datasetIndex = elements[0].datasetIndex;
                      let dataPoint = this.data.datasets[datasetIndex].data[idx];
                      if (!dataPoint.notes) {
                          for (let d of this.data.datasets) {
                              if (d.data[idx] && d.data[idx].notes) {
                                  dataPoint = d.data[idx];
                                  break;
                              }
                          }
                      }

                      if (dataPoint && dataPoint.notes) {
                          showNoteModal(dataPoint.x, dataPoint.notes, dataPoint.image_url);
                      }
                  }
              }
          }
      });
  }

  function fetchAndRenderCharts() {
      fetch(`/api/chart_data/${flockId}?mode=daily`)
          .then(response => response.json())
          .then(data => {
              if (data.charts) {
                  generalChart = initOrUpdateChart(generalChart, 'generalChart', data.charts.general);
                  hatchingEggChart = initOrUpdateChart(hatchingEggChart, 'hatchingEggChart', data.charts.hatching);
                  waterChart = initOrUpdateChart(waterChart, 'waterChart', data.charts.water);
                  feedChart = initOrUpdateChart(feedChart, 'feedChart', data.charts.feed);
                  maleChart = initOrUpdateChart(maleChart, 'maleChart', data.charts.bw_male);
                  femaleChart = initOrUpdateChart(femaleChart, 'femaleChart', data.charts.bw_female);
              }
          })
          .catch(err => console.error("Error loading chart data:", err));
  }
"""

pattern = re.compile(r'function getScaleOptions.*?function switchMode\(mode\) {', re.DOTALL)
content = pattern.sub(create_chart_initializer() + '\n  function switchMode(mode) {', content)

pattern2 = re.compile(r"document\.addEventListener\('DOMContentLoaded', \(\) => \{\n(.*?)// Update \"Switch House\" links with current hash", re.DOTALL)
def replace_dom_ready(match):
    return "document.addEventListener('DOMContentLoaded', () => {\n      fetchAndRenderCharts();\n" + match.group(1) + "// Update \"Switch House\" links with current hash"

content = pattern2.sub(replace_dom_ready, content)

with open('templates/flock_detail_modern.html', 'w') as f:
    f.write(content)

# Same for flock_detail.html
with open('templates/flock_detail.html', 'r') as f:
    content_d = f.read()

content_d = content_d.replace("const chartDataDaily = {{ chart_data | tojson }};", "")
content_d = content_d.replace("const chartDataWeekly = {{ chart_data_weekly | tojson }};", "")
content_d = pattern.sub(create_chart_initializer() + '\n  function switchMode(mode) {', content_d)
content_d = pattern2.sub(replace_dom_ready, content_d)

with open('templates/flock_detail.html', 'w') as f:
    f.write(content_d)
