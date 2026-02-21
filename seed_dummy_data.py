from app import app, db, Flock, House, DailyLog, Hatchability, Standard
from datetime import date, timedelta
import random

with app.app_context():
    # Ensure standards exist
    if Standard.query.count() == 0:
        for w in range(1, 70):
            db.session.add(Standard(
                week=w,
                std_mortality_male=0.3,
                std_mortality_female=0.3,
                std_bw_male=w*100,
                std_bw_female=w*90,
                std_egg_prod=80 if w > 24 else 0
            ))
        db.session.commit()

    # Create Flock
    house = House.query.first()
    if not house:
        house = House(name="TestHouse")
        db.session.add(house)
        db.session.commit()

    flock = Flock.query.filter_by(flock_id="TestFlock").first()
    if not flock:
        flock = Flock(
            house_id=house.id,
            flock_id="TestFlock",
            intake_date=date.today() - timedelta(days=300),
            intake_male=1000,
            intake_female=10000,
            status='Active',
            phase='Production',
            production_start_date=date.today() - timedelta(days=150)
        )
        db.session.add(flock)
        db.session.commit()

    # Create Logs (Last 80 days)
    for i in range(80):
        d = date.today() - timedelta(days=80-i)
        if not DailyLog.query.filter_by(flock_id=flock.id, date=d).first():
            log = DailyLog(
                flock_id=flock.id,
                date=d,
                mortality_female=random.randint(0, 5),
                mortality_male=random.randint(0, 1),
                eggs_collected=random.randint(8000, 9500),
                body_weight_female=2000 + (i*5),
                body_weight_male=3000 + (i*10),
                uniformity_female=random.uniform(80, 95),
                uniformity_male=random.uniform(80, 95)
            )
            db.session.add(log)
    db.session.commit()

    # Create Hatch Data
    for i in range(12): # 12 weeks
        s_date = date.today() - timedelta(weeks=12-i)
        if not Hatchability.query.filter_by(flock_id=flock.id, setting_date=s_date).first():
            h = Hatchability(
                flock_id=flock.id,
                setting_date=s_date,
                candling_date=s_date + timedelta(days=18),
                hatching_date=s_date + timedelta(days=21),
                egg_set=10000,
                hatched_chicks=random.randint(8000, 9000),
                clear_eggs=500,
                rotten_eggs=100,
                male_ratio_pct=10.5
            )
            db.session.add(h)
    db.session.commit()

    print(f"Seeded data for Flock ID: {flock.id}")
