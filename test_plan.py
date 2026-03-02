import re

with open('templates/flock_detail_readonly.html', 'r') as f:
    content = f.read()

# Replace any stray dataset-level `datalabels:` that would interfere with global toggle.
# In HatchChart, they set `anchor` and `formatter` directly. The global formatter already handles %.
# And global anchor is `end`, `align` is `top`.
# We don't want to remove these completely if they just customize display format,
# BUT dataset-level `display` overrides global. They don't have `display` here, so it's fine!
# They will just inherit `display` from global options plugins datalabels!
# Excellent!

# Wait, `datalabels:{align:'bottom'}` inside `flock_detail_readonly.html` for Egg Prod %:
# That's fine, it overrides alignment only.

# Let's verify our toggle button logic works.
# Inside `fix_charts_script.py`, we injected `_showLabels = false` default and dynamically checking.
