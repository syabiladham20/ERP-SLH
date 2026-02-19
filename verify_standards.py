from app import app, db, Standard

with app.app_context():
    # Check if new columns exist
    try:
        s = Standard.query.first()
        if s:
            print(f"Week {s.week}: EggWeight={s.std_egg_weight}, Hatch={s.std_hatchability}")
            print(f"Mort={s.std_mortality_male}, BW_M={s.std_bw_male}, BW_F={s.std_bw_female}")
        else:
            print("No standards found.")

        # Check column names explicitly via table metadata if possible
        # Or just trust query execution

    except Exception as e:
        print(f"Error accessing columns: {e}")
