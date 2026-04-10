from app import app, db, User
from werkzeug.security import generate_password_hash

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        u = User(username='admin', role='Admin', dept='All', password_hash=generate_password_hash('admin'))
        db.session.add(u)
        db.session.commit()
