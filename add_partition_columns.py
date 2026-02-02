import sqlite3
import os

db_path = os.path.join('instance', 'farm.db')

def add_columns():
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    columns_to_add = [
        ('is_weighing_day', 'BOOLEAN DEFAULT 0'),
        ('bw_male_p1', 'FLOAT DEFAULT 0.0'),
        ('bw_male_p2', 'FLOAT DEFAULT 0.0'),
        ('unif_male_p1', 'FLOAT DEFAULT 0.0'),
        ('unif_male_p2', 'FLOAT DEFAULT 0.0'),
        ('bw_female_p1', 'FLOAT DEFAULT 0.0'),
        ('bw_female_p2', 'FLOAT DEFAULT 0.0'),
        ('bw_female_p3', 'FLOAT DEFAULT 0.0'),
        ('bw_female_p4', 'FLOAT DEFAULT 0.0'),
        ('unif_female_p1', 'FLOAT DEFAULT 0.0'),
        ('unif_female_p2', 'FLOAT DEFAULT 0.0'),
        ('unif_female_p3', 'FLOAT DEFAULT 0.0'),
        ('unif_female_p4', 'FLOAT DEFAULT 0.0'),
        ('standard_bw_male', 'FLOAT DEFAULT 0.0'),
        ('standard_bw_female', 'FLOAT DEFAULT 0.0')
    ]

    for col_name, col_type in columns_to_add:
        try:
            print(f"Adding column {col_name}...")
            c.execute(f"ALTER TABLE daily_log ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print(f"Column {col_name} already exists.")
            else:
                print(f"Error adding {col_name}: {e}")

    conn.commit()
    conn.close()
    print("Database migration complete.")

if __name__ == "__main__":
    if os.path.exists(db_path):
        add_columns()
    else:
        print(f"Database not found at {db_path}")
