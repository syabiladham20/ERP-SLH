from app import db, User, app
with app.app_context():
    u = User.query.filter_by(username='admin').first()
    if not u:
        u = User(username='admin', dept='Admin', role='Admin')
        u.set_password('admin123')
        db.session.add(u)
        db.session.commit()
    else:
        u.set_password('admin123')
        db.session.commit()
