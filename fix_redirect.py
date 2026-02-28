from app import app, db, User

with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    if admin:
        admin.dept = 'Admin' # Must be 'Admin' for dept_required to allow All
        db.session.commit()
