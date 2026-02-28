import re
def add_toggle_script_detail(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    toggle_script = """  // --- Common Chart Options ---
  function toggleDataLabels(chartId, btnElement) {
      let chartInstance;
      switch(chartId) {
          case 'generalChart': chartInstance = generalChart; break;
          case 'hatchingEggChart': chartInstance = hatchingEggChart; break;
          case 'waterChart': chartInstance = waterChart; break;
          case 'feedChart': chartInstance = feedChart; break;
          case 'maleChart': chartInstance = maleChart; break;
          case 'femaleChart': chartInstance = femaleChart; break;
          case 'hatchChart': chartInstance = hatchChart; break;
      }

      if (!chartInstance) return;

      // Toggle logic
      let currentDisplay = chartInstance.options.plugins.datalabels.display;
      // If undefined, default is true due to our global Chart.defaults
      if (currentDisplay === undefined) currentDisplay = true;

      const newDisplay = !currentDisplay;
      chartInstance.options.plugins.datalabels.display = newDisplay;

      // Update button style
      if (newDisplay) {
          btnElement.classList.remove('btn-secondary');
          btnElement.classList.add('btn-outline-secondary');
      } else {
          btnElement.classList.remove('btn-outline-secondary');
          btnElement.classList.add('btn-secondary');
      }

      chartInstance.update();
  }

"""
    content = content.replace("  // --- Common Chart Options ---\n", toggle_script)

    with open(filepath, 'w') as f:
        f.write(content)

add_toggle_script_detail('templates/flock_detail.html')
