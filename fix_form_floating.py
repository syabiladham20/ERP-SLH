import re

with open('templates/daily_log_form.html', 'r') as f:
    content = f.read()

# Remove the divs from inside the form-floating
content = re.sub(
    r'<label for="feed_male_gp_bird">Male Feed \(g/bird\)</label>\s*<div class="mt-1 small text-muted">Auto Calc: <span id="live-feed-calc-male" class="fw-bold text-primary">0 kg</span></div>',
    r'<label for="feed_male_gp_bird">Male Feed (g/bird)</label>\n            </div>\n            <div class="mt-1 small text-muted px-2">Auto Calc: <span id="live-feed-calc-male" class="fw-bold text-primary">0 kg</span></div>',
    content
)

content = re.sub(
    r'<label for="feed_female_gp_bird">Female Feed \(g/bird\)</label>\s*<div class="mt-1 small text-muted">Auto Calc: <span id="live-feed-calc-female" class="fw-bold text-primary">0 kg</span></div>',
    r'<label for="feed_female_gp_bird">Female Feed (g/bird)</label>\n            </div>\n            <div class="mt-1 small text-muted px-2">Auto Calc: <span id="live-feed-calc-female" class="fw-bold text-primary">0 kg</span></div>',
    content
)

# And because we added a closing </div>, we must remove the next closing </div> to keep things balanced
male_block = """            <div class="form-floating">
              <input type="number" step="0.01" class="form-control form-control-lg" name="feed_male_gp_bird" id="feed_male_gp_bird" placeholder="Male Feed (g/bird)" value="{{ log.feed_male_gp_bird if log and log.feed_male_gp_bird else '' }}">
              <label for="feed_male_gp_bird">Male Feed (g/bird)</label>
            </div>
            <div class="mt-1 small text-muted px-2">Auto Calc: <span id="live-feed-calc-male" class="fw-bold text-primary">0 kg</span></div>
            </div>"""

fixed_male_block = """            <div class="form-floating">
              <input type="number" step="0.01" class="form-control form-control-lg" name="feed_male_gp_bird" id="feed_male_gp_bird" placeholder="Male Feed (g/bird)" value="{{ log.feed_male_gp_bird if log and log.feed_male_gp_bird else '' }}">
              <label for="feed_male_gp_bird">Male Feed (g/bird)</label>
            </div>
            <div class="mt-1 small text-muted px-2">Auto Calc: <span id="live-feed-calc-male" class="fw-bold text-primary">0 kg</span></div>"""

content = content.replace(male_block, fixed_male_block)

female_block = """            <div class="form-floating">
              <input type="number" step="0.01" class="form-control form-control-lg" name="feed_female_gp_bird" id="feed_female_gp_bird" placeholder="Female Feed (g/bird)" value="{{ log.feed_female_gp_bird if log and log.feed_female_gp_bird else '' }}">
              <label for="feed_female_gp_bird">Female Feed (g/bird)</label>
            </div>
            <div class="mt-1 small text-muted px-2">Auto Calc: <span id="live-feed-calc-female" class="fw-bold text-primary">0 kg</span></div>
            </div>"""

fixed_female_block = """            <div class="form-floating">
              <input type="number" step="0.01" class="form-control form-control-lg" name="feed_female_gp_bird" id="feed_female_gp_bird" placeholder="Female Feed (g/bird)" value="{{ log.feed_female_gp_bird if log and log.feed_female_gp_bird else '' }}">
              <label for="feed_female_gp_bird">Female Feed (g/bird)</label>
            </div>
            <div class="mt-1 small text-muted px-2">Auto Calc: <span id="live-feed-calc-female" class="fw-bold text-primary">0 kg</span></div>"""

content = content.replace(female_block, fixed_female_block)

with open('templates/daily_log_form.html', 'w') as f:
    f.write(content)
