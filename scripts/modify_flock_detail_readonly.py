import re

with open('templates/flock_detail_readonly.html', 'r') as f:
    content = f.read()

# We need to nuke the old chart rendering functions and replace them with the simplified fetch based ones.
# The functions are renderWaterChart, renderFeedChart, renderBWChart, renderGeneralChart, renderHatchingChart, renderHatchChart etc.

# Let's find where the charts functions begin.
# 'function renderWaterChart()' starts around 1195.

def create_chart_initializer():
    return """
  // Single SSOT render function!
  function initOrUpdateChart(chartVar, canvasId, chartDataGroup) {
      const ctx = document.getElementById(canvasId).getContext('2d');
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
                      // Find first dataset with a note at this index, starting from the clicked one
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

# Replace all old rendering functions up to switchMode with our new JS
pattern = re.compile(r'function getScaleOptions.*?function switchMode\(mode\) {', re.DOTALL)
content = pattern.sub(create_chart_initializer() + '\n  function switchMode(mode) {', content)

with open('templates/flock_detail_readonly.html', 'w') as f:
    f.write(content)
