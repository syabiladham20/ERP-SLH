import re

def add_toggle_buttons(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    charts = [
        ('generalChart', 'cardGeneral'),
        ('hatchingEggChart', 'cardHatching'),
        ('waterChart', 'cardWater'),
        ('feedChart', 'cardFeed'),
        ('maleChart', 'cardMale'),
        ('femaleChart', 'cardFemale')
    ]

    for chart_id, card_id in charts:
        button_html = f"""
                <button class="btn btn-sm btn-outline-secondary" title="Toggle Data Labels" onclick="toggleDataLabels('{chart_id}', this)">
                    <i class="bi bi-tag"></i>
                </button>
                <button class="btn btn-sm btn-outline-secondary" onclick="resetZoom({chart_id})" title="Reset Zoom">
"""
        content = re.sub(
            fr'<button class="btn btn-sm btn-outline-secondary" onclick="resetZoom\({chart_id}\)" title="Reset Zoom">\s*',
            button_html,
            content
        )

    with open(filepath, 'w') as f:
        f.write(content)

add_toggle_buttons('templates/flock_detail.html')
add_toggle_buttons('templates/flock_detail_readonly.html')

def add_hatch_button(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    chart_id = "hatchChart"
    button_html = f"""
                <button class="btn btn-sm btn-outline-secondary" title="Toggle Data Labels" onclick="toggleDataLabels('{chart_id}', this)">
                    <i class="bi bi-tag"></i>
                </button>
                <button class="btn btn-sm btn-outline-secondary" onclick="resetZoom({chart_id})" title="Reset Zoom">
"""
    content = re.sub(
        fr'<button class="btn btn-sm btn-outline-secondary" onclick="resetZoom\({chart_id}\)" title="Reset Zoom">\s*',
        button_html,
        content
    )
    with open(filepath, 'w') as f:
        f.write(content)

add_hatch_button('templates/flock_detail_readonly.html')


def add_toggle_script(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    toggle_script = """
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

  // Common Options
"""
    content = content.replace("  // Common Options\n", toggle_script)

    with open(filepath, 'w') as f:
        f.write(content)

add_toggle_script('templates/flock_detail.html')
add_toggle_script('templates/flock_detail_readonly.html')
