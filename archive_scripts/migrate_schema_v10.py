import sqlite3
import os

db_path = os.path.join('instance', 'farm.db')

def migrate():
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # --- Flock Table Updates ---
    flock_columns = [
        ('prod_start_male', 'INTEGER DEFAULT 0'),
        ('prod_start_female', 'INTEGER DEFAULT 0'),
        ('prod_start_male_hosp', 'INTEGER DEFAULT 0'),
        ('prod_start_female_hosp', 'INTEGER DEFAULT 0')
    ]

    print("Checking Flock table...")
    cursor.execute("PRAGMA table_info(flock)")
    existing_flock_cols = [row[1] for row in cursor.fetchall()]

    for col_name, col_type in flock_columns:
        if col_name not in existing_flock_cols:
            print(f"Adding {col_name} to flock...")
            try:
                cursor.execute(f"ALTER TABLE flock ADD COLUMN {col_name} {col_type}")
            except Exception as e:
                print(f"Error adding {col_name}: {e}")

    # --- DailyLog Table Updates ---
    log_columns = [
        ('mortality_female_hosp', 'INTEGER DEFAULT 0'),
        ('culls_female_hosp', 'INTEGER DEFAULT 0'),
        ('females_moved_to_prod', 'INTEGER DEFAULT 0'),
        ('females_moved_to_hosp', 'INTEGER DEFAULT 0')
    ]

    print("Checking DailyLog table...")
    cursor.execute("PRAGMA table_info(daily_log)")
    existing_log_cols = [row[1] for row in cursor.fetchall()]

    for col_name, col_type in log_columns:
        if col_name not in existing_log_cols:
            print(f"Adding {col_name} to daily_log...")
            try:
                cursor.execute(f"ALTER TABLE daily_log ADD COLUMN {col_name} {col_type}")
            except Exception as e:
                print(f"Error adding {col_name}: {e}")

    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == '__main__':
    migrate()
