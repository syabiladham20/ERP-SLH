from app import app, db, Hatchability, calculate_male_ratio, Flock, DailyLog

def backfill():
    with app.app_context():
        records = Hatchability.query.order_by(Hatchability.setting_date).all()
        count = 0
        updated = 0

        print(f"Found {len(records)} records to check.")

        flock_cache = {}
        logs_cache = {}
        hatchery_cache = {}

        for r in records:
            if r.flock_id not in flock_cache:
                flock_cache[r.flock_id] = db.session.get(Flock, r.flock_id)
            if r.flock_id not in logs_cache:
                logs_cache[r.flock_id] = DailyLog.query.filter_by(flock_id=r.flock_id).order_by(DailyLog.date).all()
            if r.flock_id not in hatchery_cache:
                hatchery_cache[r.flock_id] = Hatchability.query.filter_by(flock_id=r.flock_id).order_by(Hatchability.setting_date).all()

            avg_ratio, large_window = calculate_male_ratio(
                r.flock_id,
                r.setting_date,
                flock_obj=flock_cache[r.flock_id],
                logs=logs_cache[r.flock_id],
                hatchery_records=hatchery_cache[r.flock_id]
            )

            if avg_ratio is not None:
                print(f"Flock {r.flock_id} Set {r.setting_date}: Ratio {r.male_ratio_pct} -> {avg_ratio:.2f} {'(Large Window)' if large_window else ''}")
                r.male_ratio_pct = avg_ratio
                updated += 1
            else:
                print(f"Flock {r.flock_id} Set {r.setting_date}: Could not calculate ratio (No logs?)")

            count += 1
            if count % 50 == 0:
                db.session.commit()
                print("Committed batch.")

        db.session.commit()
        print(f"Finished. Updated {updated} records.")

if __name__ == '__main__':
    backfill()
