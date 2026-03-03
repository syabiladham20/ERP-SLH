from app import db, User, app
with app.app_context():
    u = User(username='farm_user', password_hash='pbkdf2:sha256:600000$xxxx', dept='Farm', role='Worker')
    u.set_password('farm123')
    db.session.add(u)
    try:
        db.session.commit()
    except:
        pass
