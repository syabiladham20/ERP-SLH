from app import app
from flask import render_template_string

with app.app_context():
    template = "{{ '{\"a\": 1}' | from_json }}"
    print(render_template_string(template))
