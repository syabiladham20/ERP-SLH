import sys
sys.path.append("/app")
from app import app, db, UIElement

with app.app_context():
    # Because init_ui_elements only inserts if the key is missing,
    # we need to manually update the existing row for the change to take effect immediately.
    e = UIElement.query.filter_by(key='nav_weight_grading').first()
    if e:
        e.section = 'navbar_health'
        e.label = 'Bodyweight'
        db.session.commit()
        print("Updated nav_weight_grading to navbar_health")
    else:
        print("UI element not found")
