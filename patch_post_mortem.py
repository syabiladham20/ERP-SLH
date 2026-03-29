with open("app.py", "r") as f:
    lines = f.readlines()

new_lines = []
in_post_mortem = False

for i, line in enumerate(lines):
    if "def health_log_post_mortem():" in line:
        in_post_mortem = True

    if in_post_mortem and "return render_template('post_mortem.html'" in line:
        new_lines.append("    houses = House.query.order_by(House.name).all()\n")
        new_lines.append("    active_flocks = Flock.query.filter_by(status='Active').all()\n")
        in_post_mortem = False

    new_lines.append(line)

with open("app.py", "w") as f:
    f.writelines(new_lines)
