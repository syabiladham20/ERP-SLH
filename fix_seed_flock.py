from run import app, db
from app.models.models import User, Farm, House, Flock, GlobalStandard
from datetime import date

with app.app_context():
    gs = GlobalStandard.query.first()
    if not gs:
        db.session.add(GlobalStandard())

    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(username='admin', dept='Farm', role='Admin')
        admin.set_password('admin')
        db.session.add(admin)

    farm = Farm.query.first()
    if not farm:
        farm = Farm(name='Farm 1')
        db.session.add(farm)
        db.session.commit()

    house = House.query.first()
    if not house:
        house = House(name='House 1', farm_id=farm.id, capacity=1000)
        db.session.add(house)
        db.session.commit()

    flock = Flock.query.first()
    if not flock:
        flock = Flock(
            name='Flock 1',
            house_id=house.id,
            strain='Test Strain',
            intake_date=date(2023, 1, 1),
            intake_male=1000,
            intake_female=10000,
            status='Active',
            phase='Production'
        )
        db.session.add(flock)
        db.session.commit()
