from app import app, db, House, Flock, DailyLog
from datetime import date

with app.app_context():
    h = House(name="Test House")
    db.session.add(h)
    db.session.commit()
    f = Flock(house_id=h.id, start_date=date(2025,1,1), initial_female_count=1000, initial_male_count=100, flock_type="production")
    db.session.add(f)
    db.session.commit()
    # Add some dummy daily logs
    for i in range(10):
        log = DailyLog(
            flock_id=f.id,
            date=date(2025,1,i+1),
            mortality_female=1,
            egg_total=500,
            water_intake_calculated=100,
            feed_female=50
        )
        db.session.add(log)
    db.session.commit()
