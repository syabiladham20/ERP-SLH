from run import app
from app import db
from app.models.models import Flock, Breed
from datetime import datetime, date

with app.app_context():
    if not Breed.query.first():
        breed = Breed(name="Ross 308")
        db.session.add(breed)
        db.session.commit()

    breed = Breed.query.first()

    if not Flock.query.first():
        flock = Flock(
            flock_id="F123",
            breed_id=breed.id,
            intake_date=datetime(2023, 1, 1).date(),
            start_of_lay_date=datetime(2023, 6, 1).date(),
            status="Production"
        )
        db.session.add(flock)
        db.session.commit()
        print("Flock created")
