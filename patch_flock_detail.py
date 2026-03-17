import re

with open('templates/flock_detail.html', 'r') as f:
    content = f.read()

# Fix the broken JS in renderWaterChart in flock_detail.html
search_str = """          tension: 0.1,
          yAxisID: 'y1',
          clip: true              clip: true
          }
      ];

      const feedScales = getScaleOptions([feedM, feedF], false);

      // Dynamic Y-axis Min Calculation"""

replace_str = """          tension: 0.1,
          yAxisID: 'y1',
          clip: true
          }
      ];

      const scales = getScaleOptions(waterData, false);

      waterChart = new Chart(document.getElementById("waterChart").getContext("2d"), {
          type: "line",
          data: {
              labels: data.dates,
              datasets: datasets
          },
          options: {
              ...commonOptions,
              onClick: null,
              scales: {
                  y: {
                      type: 'linear',
                      display: true,
                      position: 'left',
                      title: { display: true, text: 'Water (ml)' },
                      ...scales
                  },
                  y1: {
                      type: 'linear',
                      display: true,
                      position: 'right',
                      title: { display: true, text: 'Ratio' },
                      grid: { drawOnChartArea: false }
                  }
              },
              plugins: {
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
              }
          }
      });
  }

  function renderFeedChart() {
      const state = chartStates.feed;
      const fullData = chartDataDaily; // Feed is primarily daily
      const data = filterDataByDate(fullData, state.start, state.end, false);

      updateChartTitle('feedChartTitle', 'Daily Gram per Bird', data, true);

      if (feedChart) feedChart.destroy();

      const feedM = (data.feed_male || []).map(v => Math.round(v));
      const feedF = (data.feed_female || []).map(v => Math.round(v));

      const datasets = [
          {
              label: 'Feed Male (g/bird)',
              data: feedM,
              borderColor: '#0d6efd',
              backgroundColor: '#0d6efd',
              tension: 0.1,
              yAxisID: 'y',
              clip: true
          },
          {
              label: 'Feed Female (g/bird)',
              data: feedF,
              borderColor: '#dc3545',
              backgroundColor: '#dc3545',
              tension: 0.1,
              yAxisID: 'y',
              clip: true
          }
      ];

      const feedScales = getScaleOptions([feedM, feedF], false);

      // Dynamic Y-axis Min Calculation"""

if search_str in content:
    content = content.replace(search_str, replace_str)
    with open('templates/flock_detail.html', 'w') as f:
        f.write(content)
    print("flock_detail.html patched successfully!")
else:
    print("Could not find search_str in flock_detail.html")
