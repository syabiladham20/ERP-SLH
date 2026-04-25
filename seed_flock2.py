from run import app
from app import db
from app.models.models import Flock
from datetime import datetime

with app.app_context():
    if not Flock.query.first():
        flock = Flock(
            flock_id="F123",
            intake_date=datetime(2023, 1, 1).date(),
            start_of_lay_date=datetime(2023, 6, 1).date(),
            status="Production"
        )
        db.session.add(flock)
        db.session.commit()
        print("Flock created")
