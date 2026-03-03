from app import app, db, calculate_male_ratio, Flock, Hatchability, DailyLog, House, Farm
import time
from datetime import datetime, timedelta

def setup_data():
    with app.app_context():
        # Clear specific tables
        Hatchability.query.delete()
        DailyLog.query.delete()
        Flock.query.delete()
        House.query.delete()
        Farm.query.delete()
        db.session.commit()

        farm = Farm(id=1, name='Test Farm')
        db.session.add(farm)
        house = House(id=1, name='Test House')
        db.session.add(house)

        # Create a flock
        flock = Flock(id=1, intake_date=datetime.now().date(), flock_id='FLOCK1', intake_male=100, intake_female=1000, house_id=1, farm_id=1)
        db.session.add(flock)

        # Create some daily logs
        for i in range(200):
            log = DailyLog(
                flock_id=1,
                date=datetime.now().date() - timedelta(days=i),
                mortality_male=1,
                mortality_female=2
            )
            db.session.add(log)

        # Create hatchability records
        for i in range(100):
            # Wednesday, weekday=2 -> falls to non-standard -> causes N+1 querying last_hatch
            setting_d = datetime(2023, 1, 4).date() + timedelta(days=i*7) # always Wed
            hatch = Hatchability(
                flock_id=1,
                setting_date=setting_d,
                candling_date=setting_d + timedelta(days=10),
                hatching_date=setting_d + timedelta(days=21),
                egg_set=100
            )
            db.session.add(hatch)

        db.session.commit()

def run_benchmark():
    with app.app_context():
        records = Hatchability.query.filter_by(flock_id=1).order_by(Hatchability.setting_date).all()
        flock = Flock.query.get(1)
        logs = DailyLog.query.filter_by(flock_id=1).order_by(DailyLog.date).all()

        start = time.perf_counter()
        for r in records:
            calculate_male_ratio(r.flock_id, r.setting_date)
        end = time.perf_counter()
        baseline_time = end - start
        print(f"Baseline (no cache): {len(records)} calls took {baseline_time:.6f} seconds")

        start = time.perf_counter()

        # Simulated fix implementation
        hatch_cache = sorted(records, key=lambda x: x.setting_date)

        for r in records:
            last_hatch_date = None
            for h_rec in reversed(hatch_cache):
                if h_rec.setting_date < r.setting_date:
                    last_hatch_date = h_rec.setting_date
                    break

            calculate_male_ratio(r.flock_id, r.setting_date, flock_obj=flock, logs=logs, last_hatch_date=last_hatch_date)

        end = time.perf_counter()
        optimized_time = end - start
        print(f"Optimized (with cache): {len(records)} calls took {optimized_time:.6f} seconds")
        print(f"Improvement: {(baseline_time - optimized_time) / baseline_time * 100:.2f}%")

if __name__ == '__main__':
    setup_data()
    run_benchmark()
