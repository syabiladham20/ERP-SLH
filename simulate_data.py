import os
import random
from datetime import date, timedelta
from app import app, db, House, Flock, DailyLog, User
from metrics import enrich_flock_data

def simulate_data():
    with app.app_context():
        print("Starting Data Simulation...")

        # 1. Create Houses
        print("Creating Houses...")
        houses = []
        for i in range(1, 31):
            house_name = f"Sim_House_{i}"
            house = House.query.filter_by(name=house_name).first()
            if not house:
                house = House(name=house_name)
                db.session.add(house)
                print(f"Created {house_name}")
            else:
                print(f"Found {house_name}")
            houses.append(house)
        db.session.commit()

        # 2. Create Flocks
        print("Creating Flocks...")
        flocks = []
        intake_date = date(2023, 1, 1)
        for i, house in enumerate(houses):
            flock_id_str = f"{house.name}_230101_Batch1"
            flock = Flock.query.filter_by(flock_id=flock_id_str).first()

            if not flock:
                flock = Flock(
                    house_id=house.id,
                    flock_id=flock_id_str,
                    intake_date=intake_date,
                    intake_male=1000,
                    intake_female=10000,
                    status='Active',
                    phase='Production',
                    production_start_date=intake_date + timedelta(days=140) # Approx 20 weeks
                )
                db.session.add(flock)
                print(f"Created Flock {flock_id_str}")
            else:
                print(f"Found Flock {flock_id_str}")
            flocks.append(flock)
        db.session.commit()

        # 3. Generate Logs
        print("Generating Daily Logs (approx 3 years)...")
        end_date = date(2026, 1, 1)
        total_logs = 0

        for flock in flocks:
            current_date = flock.intake_date
            logs_to_add = []

            # Check existing logs to avoid duplicates
            existing_dates = set(log.date for log in DailyLog.query.filter_by(flock_id=flock.id).all())

            while current_date <= end_date:
                if current_date in existing_dates:
                    current_date += timedelta(days=1)
                    continue

                age_days = (current_date - flock.intake_date).days
                age_weeks = age_days // 7

                # Realistic-ish metrics
                # Mortality: ~0.05% daily baseline, occasional spikes
                mort_m = 0
                mort_f = 0
                if random.random() < 0.9:
                    mort_m = random.randint(0, 2)
                    mort_f = random.randint(0, 5)
                else:
                    mort_m = random.randint(2, 5)
                    mort_f = random.randint(5, 15)

                # Eggs: Ramp up to peak at week 30, then decline
                eggs = 0
                if age_weeks > 20:
                    peak_week = 30
                    if age_weeks < peak_week:
                        # Ramping up
                        factor = (age_weeks - 20) / 10
                        eggs = int(flock.intake_female * 0.9 * factor) # 90% peak
                    else:
                        # Declining
                        weeks_past_peak = age_weeks - peak_week
                        decline_factor = max(0.5, 0.9 - (weeks_past_peak * 0.005)) # Slow decline
                        eggs = int(flock.intake_female * decline_factor)

                # Feed
                feed_m = 120 + random.uniform(-5, 5) if age_weeks > 20 else 80 + random.uniform(-5, 5)
                feed_f = 160 + random.uniform(-5, 5) if age_weeks > 20 else 100 + random.uniform(-5, 5)

                log = DailyLog(
                    flock_id=flock.id,
                    date=current_date,
                    mortality_male=mort_m,
                    mortality_female=mort_f,
                    culls_male=random.randint(0, 1),
                    culls_female=random.randint(0, 2),
                    eggs_collected=eggs,
                    feed_male_gp_bird=round(feed_m, 1),
                    feed_female_gp_bird=round(feed_f, 1),
                    body_weight_male=random.randint(3000, 4500),
                    body_weight_female=random.randint(2500, 3800),
                    water_intake_calculated=random.uniform(180, 220) * (flock.intake_female + flock.intake_male) / 1000
                )
                logs_to_add.append(log)
                current_date += timedelta(days=1)

            if logs_to_add:
                db.session.bulk_save_objects(logs_to_add)
                total_logs += len(logs_to_add)
                print(f"Added {len(logs_to_add)} logs for {flock.flock_id}")

            db.session.commit() # Commit per flock to manage transaction size

        print(f"Simulation Complete. Total Logs Generated: {total_logs}")

if __name__ == "__main__":
    simulate_data()
