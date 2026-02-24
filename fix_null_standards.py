from app import app, db, Standard

def fix_null_standards():
    with app.app_context():
        # Find records with NULL values
        standards = Standard.query.filter(
            (Standard.std_cum_eggs_hha == None) | (Standard.std_cum_chicks_hha == None)
        ).all()

        if not standards:
            print("No Standard records found with NULL values in std_cum_eggs_hha or std_cum_chicks_hha.")
            return

        print(f"Found {len(standards)} records with NULL values. Fixing them...")

        count = 0
        for s in standards:
            updated = False
            if s.std_cum_eggs_hha is None:
                s.std_cum_eggs_hha = 0.0
                updated = True
            if s.std_cum_chicks_hha is None:
                s.std_cum_chicks_hha = 0.0
                updated = True

            if updated:
                count += 1
                print(f" - Fixed Standard Week {s.week} (Production Week {s.production_week})")

        if count > 0:
            db.session.commit()
            print(f"Successfully updated {count} records.")
        else:
            print("No records needed updating (values were already set but query returned them? Unexpected).")

if __name__ == "__main__":
    try:
        fix_null_standards()
    except Exception as e:
        print(f"An error occurred: {e}")
