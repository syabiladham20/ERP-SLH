from app import app, db, Flock, House, DailyLog, Hatchability, Standard
from datetime import date, timedelta
import random

with app.app_context():
    flock = Flock.query.first()
    # Create 300 more logs to really test N+1
    for i in range(80, 400):
        d = flock.intake_date + timedelta(days=i)
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
                uniformity_male=random.uniform(80, 95),
                feed_male_gp_bird=random.uniform(110, 130),
                feed_female_gp_bird=random.uniform(150, 170),
                water_intake_calculated=random.uniform(0.2, 0.3),
                flushing=(i % 10 == 0)
            )
            db.session.add(log)
    db.session.commit()
    print("Seeded 320 more logs.")
