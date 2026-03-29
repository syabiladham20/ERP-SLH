files = [
    'templates/bodyweight.html',
    'templates/post_mortem.html',
    'templates/health_log_medication.html'
]

marker = "<script>\n    document.addEventListener(\"DOMContentLoaded\", function() {\n        // Read the 'tab' URL parameter"

for file in files:
    with open(file, 'r') as f:
        content = f.read()

    # We replace everything from marker to </script>\n{% endblock %}
    import re
    cleaned = re.sub(r'<script>\n    document.addEventListener\("DOMContentLoaded", function\(\) \{\n        // Read the \'tab\' URL parameter.*?</script>\n', '', content, flags=re.DOTALL)

    with open(file, 'w') as f:
        f.write(cleaned)

print("Cleaned!")
