from app import app, db, House, Flock, DailyLog, Standard
from datetime import date

with app.app_context():
    h = House.query.first()
    if not h:
        h = House(name="Test House")
        db.session.add(h)
        db.session.commit()
    f = Flock.query.first()
    if not f:
        f = Flock(house_id=h.id, flock_id="TEST-FLOCK-1", intake_date=date(2025,1,1), intake_female=1000, intake_male=100)
        db.session.add(f)
        db.session.commit()
    # Add some dummy daily logs
    log = DailyLog.query.filter_by(flock_id=f.id).first()
    if not log:
        for i in range(10):
            log = DailyLog(
                flock_id=f.id,
                date=date(2025,1,i+1),
                mortality_female=1,
                eggs_collected=500,
                water_intake_calculated=100,
                feed_female=50
            )
            db.session.add(log)
        db.session.commit()
    print("Added data.")
