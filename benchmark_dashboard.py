import timeit
from app import app, db, House, Flock, DailyLog
from datetime import date, timedelta
import random

def setup_db():
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['TESTING'] = True
    # Suppress SQLAlchemy warnings if any
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.create_all()

    # Create House
    house = House(name='BenchmarkHouse')
    db.session.add(house)
    db.session.commit()

    # Create Flock
    intake_date = date.today() - timedelta(days=500)
    flock = Flock(
        house_id=house.id,
        batch_id='BenchmarkBatch',
        intake_date=intake_date,
        intake_male=1000,
        intake_female=10000,
        status='Active'
    )
    db.session.add(flock)
    db.session.commit()

    # Seed 500 logs
    logs = []
    # Using yesterday as the 'target_date' for the benchmark, so let's populate up to today
    for i in range(501):
        log_date = intake_date + timedelta(days=i)
        log = DailyLog(
            flock_id=flock.id,
            date=log_date,
            mortality_male=random.randint(0, 5),
            mortality_female=random.randint(0, 10),
            eggs_collected=random.randint(8000, 9500)
        )
        logs.append(log)

    db.session.bulk_save_objects(logs)
    db.session.commit()
    return flock.id

def baseline(flock_id):
    target_date = date.today() - timedelta(days=1) # Target yesterday

    # Simulate the N+1 pattern
    log_today = DailyLog.query.filter_by(flock_id=flock_id, date=target_date).first()
    log_prev = DailyLog.query.filter_by(flock_id=flock_id, date=target_date - timedelta(days=1)).first()

    all_logs = DailyLog.query.filter_by(flock_id=flock_id).filter(DailyLog.date <= target_date).order_by(DailyLog.date.asc()).all()

    return log_today, log_prev, len(all_logs)

def optimized(flock_id):
    target_date = date.today() - timedelta(days=1)

    # Simulate optimized pattern: fetch all_logs first
    all_logs = DailyLog.query.filter_by(flock_id=flock_id).filter(DailyLog.date <= target_date).order_by(DailyLog.date.asc()).all()

    # In-memory filtering
    # Since all_logs is ordered asc, log_today should be near the end.
    # Searching from end is fastest.
    log_today = None
    log_prev = None

    prev_date = target_date - timedelta(days=1)

    for l in reversed(all_logs):
        if log_today is None and l.date == target_date:
            log_today = l
        elif log_prev is None and l.date == prev_date:
            log_prev = l

        if log_today and log_prev:
            break

        # Optimization: if we pass the dates (since sorted), stop?
        # Since searching reversed (desc date), if current date < prev_date, we can stop searching for prev_date.
        if l.date < prev_date:
            break

    return log_today, log_prev, len(all_logs)

if __name__ == "__main__":
    with app.app_context():
        flock_id = setup_db()
        print(f"Database setup with flock_id: {flock_id}")

        # Verification
        b_today, b_prev, b_len = baseline(flock_id)
        o_today, o_prev, o_len = optimized(flock_id)

        assert b_len == o_len
        assert b_today.id == o_today.id if b_today else o_today is None
        assert b_prev.id == o_prev.id if b_prev else o_prev is None

        print("Verification passed: Logic is equivalent.")

        number = 100
        t_baseline = timeit.timeit(lambda: baseline(flock_id), number=number)
        t_optimized = timeit.timeit(lambda: optimized(flock_id), number=number)

        avg_baseline = (t_baseline / number) * 1000
        avg_optimized = (t_optimized / number) * 1000

        print(f"Baseline (avg over {number} runs): {avg_baseline:.2f} ms")
        print(f"Optimized (avg over {number} runs): {avg_optimized:.2f} ms")
        print(f"Improvement: {(avg_baseline - avg_optimized):.2f} ms per request ({(avg_baseline / avg_optimized):.2f}x faster)")
