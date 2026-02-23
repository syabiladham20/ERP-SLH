from app import app, db, Standard

def backfill_standard_production_week():
    with app.app_context():
        standards = Standard.query.order_by(Standard.week.asc()).all()

        # Find start of production (first week with egg prod > 0)
        start_week = None
        for s in standards:
            if s.std_egg_prod > 0:
                start_week = s.week
                break

        if start_week is None:
            print("No production standards found (egg_prod > 0). Defaulting to Week 24.")
            start_week = 24

        count = 0
        prod_counter = 1

        for s in standards:
            if s.week >= start_week:
                if s.production_week != prod_counter:
                    s.production_week = prod_counter
                    count += 1
                prod_counter += 1
            else:
                if s.production_week is not None:
                    s.production_week = None
                    count += 1

        if count > 0:
            db.session.commit()
            print(f"Successfully updated {count} standard records.")
        else:
            print("No updates needed.")

if __name__ == "__main__":
    backfill_standard_production_week()
