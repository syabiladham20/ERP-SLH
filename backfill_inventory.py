from app import app, db, Flock, DailyLog

def backfill_inventory():
    with app.app_context():
        # Iterate over all flocks
        flocks = Flock.query.all()
        for flock in flocks:
            # We want to recalculate inventory from the intake counts
            curr_males = flock.intake_male if flock.intake_male is not None else 0
            curr_females = flock.intake_female if flock.intake_female is not None else 0

            # Fetch daily logs ordered by date
            logs = DailyLog.query.filter_by(flock_id=flock.id).order_by(DailyLog.date.asc()).all()

            for log in logs:
                # Assign start of day counts
                log.males_at_start = curr_males
                log.females_at_start = curr_females

                # Deduct today's mortality/culls
                total_male_out = (log.mortality_male or 0) + (log.mortality_male_hosp or 0) + (log.culls_male or 0) + (log.culls_male_hosp or 0)
                total_female_out = (log.mortality_female or 0) + (log.mortality_female_hosp or 0) + (log.culls_female or 0) + (log.culls_female_hosp or 0)

                curr_males -= total_male_out
                curr_females -= total_female_out

        try:
            db.session.commit()
            print("✅ Inventory backfill completed successfully.")
        except Exception as e:
            db.session.rollback()
            print(f"⚠️ Error during backfill: {e}")

if __name__ == '__main__':
    backfill_inventory()
