import os
from app import app, db, User

def seed_user():
    with app.app_context():
        user = User.query.filter_by(username='farm_user').first()
        if not user:
            user = User(username='farm_user', role='Worker', dept='Farm', farm_id=1)
            user.set_password('farm123')
            db.session.add(user)
            db.session.commit()
            print("Test user created: farm_user / farm123")

        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            admin_user = User(username='admin', role='Admin', dept='Admin', farm_id=None)
            admin_user.set_password('admin123')
            db.session.add(admin_user)
            db.session.commit()
            print("Admin user created: admin / admin123")
        else:
            admin_user.set_password('admin123')
            db.session.commit()
            print("Admin user password reset to admin123")

if __name__ == '__main__':
    seed_user()
