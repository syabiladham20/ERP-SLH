from run import app, db
from app.models.models import House, Farm, Flock, GlobalStandard, User
import datetime

with app.app_context():
    farm = Farm(name='Test Farm')
    db.session.add(farm)
    db.session.commit()

    h = House(name='Test House')
    db.session.add(h)
    db.session.commit()

    f = Flock(farm_id=farm.id, house_id=h.id, flock_id='test1', intake_date=datetime.date.today(), status='Active')
    db.session.add(f)
    db.session.commit()
