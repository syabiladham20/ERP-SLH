from app import app, db, Flock, DailyLog

with app.app_context():
    flocks = Flock.query.all()
    for f in flocks:
        if not f.start_of_lay_date:
            first_egg_log = DailyLog.query.filter_by(flock_id=f.id).filter(DailyLog.eggs_collected > 0).order_by(DailyLog.date).first()
            if first_egg_log:
                f.start_of_lay_date = first_egg_log.date
                db.session.commit()
                print(f"Set Start of Lay for {f.flock_id} to {f.start_of_lay_date}")
