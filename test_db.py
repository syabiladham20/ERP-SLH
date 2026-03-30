from app import app, db, User

with app.app_context():
    print("User queries properly:", User.query.first())
