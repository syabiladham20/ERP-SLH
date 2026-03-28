from app import app, db, User, GlobalStandard
with app.app_context():
    u = User.query.filter_by(username='admin').first()
    if not u:
        u = User(username='admin', role='Admin', dept='Farm')
        u.set_password('admin123')
        db.session.add(u)
    else:
        u.set_password('admin123')

    gs = GlobalStandard.query.first()
    if not gs:
        gs = GlobalStandard()
        db.session.add(gs)

    db.session.commit()
    print("Created test user: admin/admin123")
