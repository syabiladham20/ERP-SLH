from app import db, app, Medication, Flock
from datetime import datetime, timedelta

with app.app_context():
    flock = Flock.query.first()
    if flock:
        # Get start of data
        start_date = datetime.strptime("2026-02-15", "%Y-%m-%d")
        end_date = datetime.strptime("2026-02-25", "%Y-%m-%d")
        # Make a med for a week
        med = Medication(
            flock_id=flock.id,
            drug_name="TestMeds3",
            start_date=start_date.date(),
            end_date=end_date.date(),
            dosage="10mg"
        )
        db.session.add(med)
        db.session.commit()
        print(f"Meds seeded from {start_date} to {end_date}")
