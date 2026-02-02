from app import app, db, Flock, DailyLog, House
from datetime import date, timedelta

def verify_logic():
    with app.app_context():
        # Setup
        db.drop_all()
        db.create_all()

        h = House(name="TestHouse")
        db.session.add(h)
        db.session.commit()

        d0 = date.today() - timedelta(days=3)
        f = Flock(
            house_id=h.id,
            batch_id="TestBatch",
            intake_date=d0,
            intake_male=1000,
            intake_female=1000,
            status='Active',
            production_start_date=d0 + timedelta(days=1) # Day 1 is rearing, Day 2 (d0+1) is Prod
        )
        db.session.add(f)
        db.session.commit()

        # Log 1 (Day 1 - Rearing)
        l1 = DailyLog(
            flock_id=f.id,
            date=d0,
            mortality_male=10,
            mortality_female=10
        )
        db.session.add(l1)

        # Log 2 (Day 2 - Prod Start)
        # Mort 5 M (Prod). Transfer 50 M to Hosp.
        l2 = DailyLog(
            flock_id=f.id,
            date=d0 + timedelta(days=1),
            mortality_male=5,
            mortality_female=0,
            males_moved_to_hosp=50
        )
        db.session.add(l2)

        # Log 3 (Day 3)
        # Mort 2 M (Hosp), 1 M (Prod).
        l3 = DailyLog(
            flock_id=f.id,
            date=d0 + timedelta(days=2),
            mortality_male=1,
            mortality_male_hosp=2,
            mortality_female=0
        )
        db.session.add(l3)

        db.session.commit()

        # --- RUN LOGIC ---
        # Copying logic from app.py index route
        logs = DailyLog.query.filter_by(flock_id=f.id).order_by(DailyLog.date.asc()).all()

        rearing_mort_m = 0
        prod_mort_m = 0
        prod_start_stock_m = f.intake_male
        prod_start_date = f.production_start_date

        curr_m_prod = f.intake_male
        curr_m_hosp = 0
        curr_f = f.intake_female

        in_production = False

        print(f"Start: M_Prod={curr_m_prod}, M_Hosp={curr_m_hosp}")

        for l in logs:
            if not in_production:
                if prod_start_date and l.date >= prod_start_date:
                    in_production = True
                    prod_start_stock_m = curr_m_prod
                    print(f"entered prod on {l.date}. Start Stock M = {prod_start_stock_m}")
                elif not prod_start_date and l.eggs_collected > 0:
                    in_production = True
                    prod_start_stock_m = curr_m_prod

            if in_production:
                prod_mort_m += l.mortality_male
            else:
                rearing_mort_m += l.mortality_male

            mort_m_prod = l.mortality_male
            mort_m_hosp = getattr(l, 'mortality_male_hosp', 0)

            cull_m_prod = l.culls_male
            cull_m_hosp = getattr(l, 'culls_male_hosp', 0)

            moved_to_hosp = getattr(l, 'males_moved_to_hosp', 0)
            moved_to_prod = getattr(l, 'males_moved_to_prod', 0)

            curr_m_prod = curr_m_prod - mort_m_prod - cull_m_prod - moved_to_hosp + moved_to_prod
            curr_m_hosp = curr_m_hosp - mort_m_hosp - cull_m_hosp + moved_to_hosp - moved_to_prod

            curr_f -= (l.mortality_female + l.culls_female)

            print(f"After {l.date}: M_Prod={curr_m_prod}, M_Hosp={curr_m_hosp}")

        print(f"Final M_Prod: {curr_m_prod} (Expected: 934)")
        print(f"Final M_Hosp: {curr_m_hosp} (Expected: 48)")

if __name__ == "__main__":
    verify_logic()
