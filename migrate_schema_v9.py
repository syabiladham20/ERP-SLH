import sqlite3
import os

base_dir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(base_dir, 'instance', 'farm.db')

def add_doses_per_unit_column():
    print(f"Connecting to database at: {db_path}")
    if not os.path.exists(db_path):
        print("Database file not found!")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column exists
        cursor.execute("PRAGMA table_info(vaccine)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'doses_per_unit' not in columns:
            print("Adding 'doses_per_unit' column to 'vaccine' table...")
            cursor.execute("ALTER TABLE vaccine ADD COLUMN doses_per_unit INTEGER DEFAULT 1000")
            conn.commit()
            print("Migration successful: added 'doses_per_unit' to 'vaccine'.")
        else:
            print("'doses_per_unit' column already exists in 'vaccine'.")

    except Exception as e:
        print(f"Error during migration: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    add_doses_per_unit_column()
