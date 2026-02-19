import pandas as pd
from app import app, db, Standard

def seed_standards():
    print("Seeding standards from SLH Daily Aviagen.xlsx...")

    try:
        # Load the Excel file
        # Standard BW starts at row 507 (0-indexed 506? No, process_import uses skiprows=507 so row 508 is index 0?)
        # Let's align with process_import logic: skiprows=507 means row 508 is index 0.
        # But previous inspection showed valid data there.

        df = pd.read_excel('SLH Daily Aviagen.xlsx', sheet_name='TEMPLATE', header=None, skiprows=507, nrows=70)

        # Columns based on inspection:
        # 0: Week
        # 14: Standard Mortality % (e.g. 0.003 for 0.3%)
        # 32: Std Male BW
        # 33: Std Female BW
        # 19: Egg Prod % (Empty in file but mapped)
        # 27: Egg Weight (Empty)
        # 26: Hatchability (Empty)

        with app.app_context():
            # Clear existing standards? Or update?
            # Standard table has unique constraint on week.
            # Let's upsert.

            count = 0
            for index, row in df.iterrows():
                try:
                    week_val = int(row[0])
                except (ValueError, TypeError):
                    continue

                std_mort = float(row[14]) * 100 if pd.notna(row[14]) else 0.0 # Convert 0.003 to 0.3 if needed?
                # Wait, inspection showed 0.003. Usually displayed as %. 0.3% is reasonable daily? Or weekly?
                # Header says "STANDARD MORTALITY%". 0.003 is 0.3%.
                # app.py uses float. Let's store as percentage value (0.3).

                std_bw_m = int(row[32]) if pd.notna(row[32]) else 0
                std_bw_f = int(row[33]) if pd.notna(row[33]) else 0

                # Missing Data placeholders
                std_egg_prod = 0.0
                std_egg_weight = 0.0
                std_hatch = 0.0

                # Check existing
                s = Standard.query.filter_by(week=week_val).first()
                if not s:
                    s = Standard(week=week_val)
                    db.session.add(s)

                s.std_mortality_male = std_mort # Using same for both sexes if only one col
                s.std_mortality_female = std_mort
                s.std_bw_male = std_bw_m
                s.std_bw_female = std_bw_f
                s.std_egg_prod = std_egg_prod
                s.std_egg_weight = std_egg_weight
                s.std_hatchability = std_hatch

                count += 1

            db.session.commit()
            print(f"Seeded/Updated {count} weeks of standards.")

    except Exception as e:
        print(f"Error seeding standards: {e}")

if __name__ == '__main__':
    seed_standards()
