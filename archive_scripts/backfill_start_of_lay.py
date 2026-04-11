from app import app, db, Flock, DailyLog
from sqlalchemy import func

def backfill_start_of_lay():
    with app.app_context():
        flocks = Flock.query.all()
        count = 0
        for flock in flocks:
            # Find earliest log with eggs
            first_egg_log = DailyLog.query.filter(
                DailyLog.flock_id == flock.id,
                DailyLog.eggs_collected > 0
            ).order_by(DailyLog.date.asc()).first()

            if first_egg_log:
                if flock.start_of_lay_date != first_egg_log.date:
                    flock.start_of_lay_date = first_egg_log.date
                    print(f"Updated Flock {flock.flock_id}: Start of Lay = {first_egg_log.date}")
                    count += 1
            else:
                pass # No eggs found

        if count > 0:
            db.session.commit()
            print(f"Successfully backfilled {count} flocks.")
        else:
            print("No updates needed.")

if __name__ == "__main__":
    backfill_start_of_lay()
