from app import db, User, app
import os

def upgrade_user():
    with app.app_context():
        user = User.query.filter_by(username="farm_user").first()
        if user:
            user.role = 'Management'
            db.session.commit()
            print("User upgraded to Management")
        else:
            print("User not found")

if __name__ == '__main__':
    upgrade_user()