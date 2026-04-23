from run import app
from app import db
from app.models.models import User
from werkzeug.security import generate_password_hash

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password_hash=generate_password_hash('admin'), role='Admin')
        db.session.add(admin)
        db.session.commit()
        print("Admin user created.")
