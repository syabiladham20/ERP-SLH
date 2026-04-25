from run import app
from app import db
from app.models.models import Flock, House, Farm
from datetime import datetime
with app.app_context():
    farm = Farm(name="F1")
    db.session.add(farm)
    db.session.commit()
    house = House(name="H1")
    db.session.add(house)
    db.session.commit()
    flock = Flock(flock_id="F123", house_id=house.id, farm_id=farm.id, intake_date=datetime(2023,1,1).date())
    db.session.add(flock)
    db.session.commit()
    print("Flock ID: " + str(flock.id))
