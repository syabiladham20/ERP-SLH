import sqlite3
import os

base_dir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(base_dir, 'instance', 'farm.db')

def add_actual_date_column():
    print(f"Connecting to database at: {db_path}")
    if not os.path.exists(db_path):
        print("Database file not found!")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column exists
        cursor.execute("PRAGMA table_info(sampling_event)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'actual_date' not in columns:
            print("Adding 'actual_date' column to 'sampling_event' table...")
            cursor.execute("ALTER TABLE sampling_event ADD COLUMN actual_date DATE")
            conn.commit()
            print("Migration successful.")
        else:
            print("'actual_date' column already exists.")

    except Exception as e:
        print(f"Error during migration: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    add_actual_date_column()
