import re

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # 1. Update toggleDataLabels function
    new_toggle = """function toggleDataLabels(chartId, btnElement) {
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

      // Toggle logic using custom _showLabels flag
      let currentDisplay = chartInstance.options.plugins.datalabels._showLabels;
      if (currentDisplay === undefined) currentDisplay = false;

      const newDisplay = !currentDisplay;
      chartInstance.options.plugins.datalabels._showLabels = newDisplay;

      // Update button style
      if (newDisplay) {
          btnElement.classList.remove('btn-outline-secondary');
          btnElement.classList.add('btn-secondary');
      } else {
          btnElement.classList.remove('btn-secondary');
          btnElement.classList.add('btn-outline-secondary');
      }

      chartInstance.update();
  }"""
    # Replace the old toggleDataLabels function
    content = re.sub(r'function toggleDataLabels\([^)]*\)\s*\{.*?(?=const commonOptions =)', new_toggle + '\n\n  ', content, flags=re.DOTALL)

    # 2. Update commonOptions datalabels to use dynamic display function based on standard/std labels
    display_func = """          datalabels: {
              _showLabels: false,
              display: function(context) {
                  const label = context.dataset.label || '';
                  if (label.toLowerCase().includes('std') || label.toLowerCase().includes('standard')) {
                      return false; // Never show labels for standard metrics
                  }
                  if (label.toLowerCase() === 'clinical notes') {
                      return false;
                  }
                  return context.chart.options.plugins.datalabels._showLabels || false;
              },
              align: 'top',
              anchor: 'end',"""
    content = re.sub(r'          datalabels: \{\s*align: \'top\',\s*anchor: \'end\',', display_func, content)

    # In flock_detail.html, there's a hardcoded datalabels display false override in options for the generalChart. Let's remove any nested display functions in the dataset declarations
    content = re.sub(r',\s*datalabels:\s*\{\s*display:\s*false\s*\}', '', content)
    content = re.sub(r',\s*datalabels:\s*\{\s*display:\s*function[^}]+\}\s*\}', '', content)
    content = re.sub(r',\s*datalabels:\s*\{\s*align:\s*\'bottom\',\s*anchor:\s*\'start\'\s*\}', '', content)

    # Remove nested datalabels in options plugin blocks if present in custom charts
    # "datalabels: { display: false }," inside hatchingEggChart options etc.
    content = re.sub(r'              datalabels:\s*\{\s*display:\s*false\s*\},?\n', '', content)

    # Make sure we don't accidentally leave options with broken syntax
    with open(filepath, 'w') as f:
        f.write(content)
    print(f"Processed {filepath}")

process_file('templates/flock_detail.html')
process_file('templates/flock_detail_readonly.html')
