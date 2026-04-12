from app import app, db, User

with app.app_context():
    if not User.query.filter_by(username='admin').first():
        u = User(username='admin', dept='Admin', role='Admin')
        u.set_password('admin123')
        db.session.add(u)
        db.session.commit()
        print("Admin user created.")
    else:
        print("Admin user exists.")
