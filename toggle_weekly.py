import re

def insert_hatching_toggle(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # Find the Hatching Egg chart header and add the Daily/Weekly toggle inside the ms-auto section
    button_html = """                <div class="btn-group btn-group-sm ms-2 me-2" role="group">
                    <input type="radio" class="btn-check" name="chartModeHatching" id="modeDailyHatching" autocomplete="off" checked onchange="switchModeHatching('daily')">
                    <label class="btn btn-outline-secondary" for="modeDailyHatching">Daily</label>
                    <input type="radio" class="btn-check" name="chartModeHatching" id="modeWeeklyHatching" autocomplete="off" onchange="switchModeHatching('weekly')">
                    <label class="btn btn-outline-secondary" for="modeWeeklyHatching">Weekly</label>
                </div>
                <!-- Per-Chart Date Picker -->"""

    content = content.replace("<!-- Per-Chart Date Picker -->", button_html, 1)

    with open(filepath, 'w') as f:
        f.write(content)

def add_switch_script(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # Add `currentModeHatching` and `switchModeHatching` logic
    content = content.replace("let currentMode = 'daily';", "let currentMode = 'daily';\n  let currentModeHatching = 'daily';")

    script_html = """
  function switchModeHatching(mode) {
      currentModeHatching = mode;
      renderHatchingChart();
  }
"""
    content = content.replace("  function switchMode(mode) {\n      currentMode = mode;\n      renderGeneralChart();\n      renderHatchingChart();\n  }",
                              "  function switchMode(mode) {\n      currentMode = mode;\n      renderGeneralChart();\n  }\n" + script_html)

    # Update renderHatchingChart to use `currentModeHatching`
    content = content.replace("function renderHatchingChart() {\n      const mode = currentMode;", "function renderHatchingChart() {\n      const mode = currentModeHatching;")

    with open(filepath, 'w') as f:
        f.write(content)


insert_hatching_toggle('templates/flock_detail.html')
insert_hatching_toggle('templates/flock_detail_readonly.html')

add_switch_script('templates/flock_detail.html')
add_switch_script('templates/flock_detail_readonly.html')
