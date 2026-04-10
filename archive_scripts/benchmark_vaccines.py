import time
import os
from datetime import date
from sqlalchemy import or_

os.environ['DATABASE_URL'] = 'sqlite:///test_benchmark.db'

from app import app, db, Vaccine, DailyLog, Flock, House

def setup_data():
    with app.app_context():
        db.drop_all()
        db.create_all()

        house = House(name="Benchmark House")
        db.session.add(house)
        db.session.commit()

        flock = Flock(
            house_id=house.id,
            flock_id="BENCHMARK-FLOCK",
            intake_date=date(2025, 1, 1),
            production_start_date=date(2025, 1, 2)
        )
        db.session.add(flock)
        db.session.commit()

        log = DailyLog(
            flock_id=flock.id,
            date=date(2025, 1, 10)
        )
        db.session.add(log)
        db.session.commit()

        vaccine_ids = []
        for i in range(50):
            vac = Vaccine(
                flock_id=flock.id,
                vaccine_name=f"Vaccine {i}",
                route="Injection",
                est_date=date(2025, 1, 10),
                age_code=f"D{i+1}"
            )
            db.session.add(vac)
            db.session.flush()
            vaccine_ids.append(vac.id)

        db.session.commit()

        return flock.id, log.id, vaccine_ids

def run_n_plus_1_benchmark(flock_id, log_id, vaccine_present_ids, vaccine_completed_ids, iterations=100):
    total_time = 0
    with app.app_context():
        log = DailyLog.query.get(log_id)
        log_date = log.date
        flock_id_check = log.flock_id

        for _ in range(iterations):
            db.session.expunge_all()

            start_time = time.time()
            for vid in vaccine_present_ids:
                vac = Vaccine.query.get(vid)
                if vac and vac.flock_id == flock_id_check:
                    if vid in vaccine_completed_ids:
                        vac.actual_date = log_date
                    elif vac.actual_date == log_date:
                        vac.actual_date = None
            end_time = time.time()
            total_time += (end_time - start_time)

    return total_time / iterations

def run_bulk_benchmark(flock_id, log_id, vaccine_present_ids, vaccine_completed_ids, iterations=100):
    total_time = 0
    with app.app_context():
        log = DailyLog.query.get(log_id)
        log_date = log.date
        flock_id_check = log.flock_id

        int_vaccine_present_ids = [int(vid) for vid in vaccine_present_ids]

        for _ in range(iterations):
            db.session.expunge_all()

            start_time = time.time()

            vaccines = Vaccine.query.filter(Vaccine.id.in_(int_vaccine_present_ids)).all()
            for vac in vaccines:
                if vac.flock_id == flock_id_check:
                    if str(vac.id) in vaccine_completed_ids:
                        vac.actual_date = log_date
                    elif vac.actual_date == log_date:
                        vac.actual_date = None

            end_time = time.time()
            total_time += (end_time - start_time)

    return total_time / iterations

if __name__ == "__main__":
    print("Setting up test data...")
    flock_id, log_id, all_vaccine_ids = setup_data()

    vaccine_present_ids = [str(vid) for vid in all_vaccine_ids]
    vaccine_completed_ids = [str(vid) for vid in all_vaccine_ids[:25]]

    print(f"Benchmarking with {len(vaccine_present_ids)} vaccines present, {len(vaccine_completed_ids)} completed.")

    iterations = 50
    print(f"Running N+1 benchmark ({iterations} iterations)...")
    n1_time = run_n_plus_1_benchmark(flock_id, log_id, vaccine_present_ids, vaccine_completed_ids, iterations)

    print(f"Running Bulk benchmark ({iterations} iterations)...")
    bulk_time = run_bulk_benchmark(flock_id, log_id, vaccine_present_ids, vaccine_completed_ids, iterations)

    print("\n" + "="*40)
    print("BENCHMARK RESULTS (Average per request)")
    print("="*40)
    print(f"N+1 Queries:   {n1_time:.5f} seconds")
    print(f"Bulk Fetch:    {bulk_time:.5f} seconds")

    if n1_time > 0:
        improvement = ((n1_time - bulk_time) / n1_time) * 100
        speedup = n1_time / bulk_time if bulk_time > 0 else float('inf')
        print(f"Improvement:   {improvement:.2f}% faster")
        print(f"Speedup:       {speedup:.2f}x faster")

    if os.path.exists('test_benchmark.db'):
        os.remove('test_benchmark.db')
