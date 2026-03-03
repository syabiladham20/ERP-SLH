from app import db, app, GlobalStandard
with app.app_context():
    if GlobalStandard.query.count() == 0:
        db.session.add(GlobalStandard(login_required=False))
        db.session.commit()
