from app import app, db, GlobalStandard

with app.app_context():
    gs = GlobalStandard.query.first()
    if gs:
        gs.login_required = False
        db.session.commit()
    else:
        gs = GlobalStandard(login_required=False)
        db.session.add(gs)
        db.session.commit()
