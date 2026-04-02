with open('app.py', 'r') as f:
    content = f.read()

content = content.replace(r"return render_template(\'flock_detail_modern.html\'", "return render_template('flock_detail_modern.html'")
content = content.replace(r"return render_template(\'flock_detail_readonly.html\'", "return render_template('flock_detail_readonly.html'")

with open('app.py', 'w') as f:
    f.write(content)
