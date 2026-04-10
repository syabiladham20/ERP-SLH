import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import os

import importlib.util
import sys
spec = importlib.util.spec_from_file_location("main_app", os.path.join(os.path.dirname(__file__), '..', 'app.py'))
main_app = importlib.util.module_from_spec(spec)
sys.modules["main_app"] = main_app
spec.loader.exec_module(main_app)
app = main_app.app
db = main_app.db
User = main_app.User

from werkzeug.security import generate_password_hash

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        u = User(username='admin', role='Admin', dept='All', password_hash=generate_password_hash('admin'))
        db.session.add(u)
        db.session.commit()
