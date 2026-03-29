import re

with open("app.py", "r") as f:
    content = f.read()

# Fix Timezone
content = content.replace("pytz.timezone('Asia/Kuala Lumpur')", "pytz.timezone('Asia/Kuala_Lumpur')")

# Fix Routes and endpoint names
content = content.replace("@app.route('/post_mortem', methods=['GET', 'POST'])", "@app.route('/health_log/post_mortem', methods=['GET', 'POST'])")
content = content.replace("def post_mortem():", "def health_log_post_mortem():")

content = content.replace("@app.route('/bodyweight', methods=['GET', 'POST'])", "@app.route('/health_log/bodyweight', methods=['GET', 'POST'])")
content = content.replace("def bodyweight():", "def health_log_bodyweight():")

# Replace all url_for
content = content.replace("url_for('post_mortem')", "url_for('health_log_post_mortem')")
content = content.replace("url_for('bodyweight')", "url_for('health_log_bodyweight')")

with open("app.py", "w") as f:
    f.write(content)
