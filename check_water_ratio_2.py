from app import app, db, DailyLog, Flock
from metrics import enrich_flock_data

with app.app_context():
    flock = Flock.query.first()
    logs = DailyLog.query.filter_by(flock_id=flock.id).order_by(DailyLog.date).all()
    if logs:
        enriched = enrich_flock_data(flock, logs)
        print("Sample enriched logs with water_feed_ratio (middle of flock):")
        for d in enriched[30:35]:
            feed_m = getattr(d['log'], 'feed_male', 0) or 0
            feed_f = getattr(d['log'], 'feed_female', 0) or 0
            water = getattr(d['log'], 'water_intake_calculated', 0) or 0
            print(f"Date: {d['log'].date}, water_intake: {water}, feed_m_kg: {feed_m}, feed_f_kg: {feed_f}, Ratio: {d['water_feed_ratio']}")
    else:
        print("No logs found.")
