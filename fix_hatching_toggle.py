import re

def fix_hatching_html(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # It seems I replaced the FIRST occurrence of <!-- Per-Chart Date Picker --> which was in General Performance chart.
    # Let's fix that.

    # Revert the wrongly injected block:
    wrong_block = """                <div class="btn-group btn-group-sm ms-2 me-2" role="group">
                    <input type="radio" class="btn-check" name="chartModeHatching" id="modeDailyHatching" autocomplete="off" checked onchange="switchModeHatching('daily')">
                    <label class="btn btn-outline-secondary" for="modeDailyHatching">Daily</label>
                    <input type="radio" class="btn-check" name="chartModeHatching" id="modeWeeklyHatching" autocomplete="off" onchange="switchModeHatching('weekly')">
                    <label class="btn btn-outline-secondary" for="modeWeeklyHatching">Weekly</label>
                </div>
                <!-- Per-Chart Date Picker -->"""
    content = content.replace(wrong_block, "<!-- Per-Chart Date Picker -->")

    # Now find the exact Hatching Egg chart header and inject it there
    # Look for: <span id="hatchingEggChartTitle" class="fw-bold mb-2 mb-md-0">Hatching Egg & Culls</span>
    # Followed by <div class="d-flex flex-wrap gap-2 align-items-center ms-auto">
    # And then <!-- Per-Chart Date Picker -->

    target_block = """<span id="hatchingEggChartTitle" class="fw-bold mb-2 mb-md-0">Hatching Egg & Culls</span>
            <div class="d-flex flex-wrap gap-2 align-items-center ms-auto">
                <!-- Per-Chart Date Picker -->"""

    # detail.html has slightly different classes sometimes, let's use regex
    new_block = """<span id="hatchingEggChartTitle" class="fw-bold mb-2 mb-md-0">Hatching Egg & Culls</span>
            <div class="d-flex flex-wrap gap-2 align-items-center ms-auto">
                <div class="btn-group btn-group-sm ms-2 me-2" role="group">
                    <input type="radio" class="btn-check" name="chartModeHatching" id="modeDailyHatching" autocomplete="off" checked onchange="switchModeHatching('daily')">
                    <label class="btn btn-outline-secondary" for="modeDailyHatching">Daily</label>
                    <input type="radio" class="btn-check" name="chartModeHatching" id="modeWeeklyHatching" autocomplete="off" onchange="switchModeHatching('weekly')">
                    <label class="btn btn-outline-secondary" for="modeWeeklyHatching">Weekly</label>
                </div>
                <!-- Per-Chart Date Picker -->"""

    content = re.sub(
        r'<span id="hatchingEggChartTitle"[^>]*>Hatching Egg & Culls</span>\s*<div class="d-flex flex-wrap gap-2 align-items-center ms-auto">\s*<!-- Per-Chart Date Picker -->',
        new_block,
        content
    )

    with open(filepath, 'w') as f:
        f.write(content)

fix_hatching_html('templates/flock_detail.html')
fix_hatching_html('templates/flock_detail_readonly.html')
