import re

with open("app.py", "r") as f:
    content = f.read()

# Replace _generate_chart_payload block
start_sig = "def _generate_chart_payload("
end_sig = "def get_chart_data("

start_idx = content.find(start_sig)
end_idx = content.find(end_sig)

if start_idx != -1 and end_idx != -1:
    old_func = content[start_idx:end_idx]

    with open("replacement.py", "r") as f2:
        new_func = f2.read()

    # We will replace it using git merge diff approach or directly replacing the string
    content = content[:start_idx] + new_func + "\n" + content[end_idx:]
    with open("app.py", "w") as f:
        f.write(content)
    print("Function replaced.")
else:
    print("Could not find function signatures.")
