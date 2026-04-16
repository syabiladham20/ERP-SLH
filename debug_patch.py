with open('app/templates/daily_log_form.html', 'r') as f:
    content = f.read()

print("Found prefillPreviousData?", "function prefillPreviousData" in content)
print("Found Initialize window.onload?", "window.onload = function()" in content)
