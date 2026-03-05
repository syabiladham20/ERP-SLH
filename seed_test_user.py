from app import app, db, User
from werkzeug.security import generate_password_hash

with app.app_context():
    # Create admin user if it doesn't exist
    user = User.query.filter_by(username='admin').first()
    if not user:
        user = User(
            username='admin',
            password_hash=generate_password_hash('admin123'),
            department='Admin',
            is_active=True
        )
        db.session.add(user)
        db.session.commit()
        print("Admin user created.")
    else:
        print("Admin user already exists.")
