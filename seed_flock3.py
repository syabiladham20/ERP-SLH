from run import app
from app import db
from app.models.models import Farm, House, Flock
from datetime import datetime

with app.app_context():
    if not Farm.query.first():
        farm = Farm(name="Main Farm")
        db.session.add(farm)
        db.session.commit()

    farm = Farm.query.first()

    if not House.query.first():
        house = House(name="House 1", farm_id=farm.id)
        db.session.add(house)
        db.session.commit()

    house = House.query.first()

    if not Flock.query.first():
        flock = Flock(
            flock_id="F123",
            farm_id=farm.id,
            house_id=house.id,
            intake_date=datetime(2023, 1, 1).date(),
            start_of_lay_date=datetime(2023, 6, 1).date(),
            status="Production"
        )
        db.session.add(flock)
        db.session.commit()
        print("Flock created")
