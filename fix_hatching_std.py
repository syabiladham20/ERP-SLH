import re
with open('templates/flock_detail.html', 'r') as f:
    content = f.read()

# Wait, `flock_detail.html` doesn't have `renderHatchChart`?
# In `flock_detail.html`, it has `hatchingEggChart` and `hatchingEggChartTitle` ("Hatching Egg & Culls").
# The prompt: "add standard hatchability % in fertility and hatchability if not yet added"
# Does `flock_detail.html` have "Fertility and Hatchability" chart?
# Let's check `flock_detail.html` for "hatchChart" or "Fertility"

start = content.find("Fertility")
print(f"Fertility in flock_detail.html: {start}")
