import sqlite3
import os

def patch_db():
    db_path = '/home/syabiladham/erpslh/instance/erp.db'

    print(f"Applying surgical patch to: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Add males_at_start
        try:
            cursor.execute("ALTER TABLE daily_log ADD COLUMN males_at_start INTEGER;")
            print("✅ Column 'males_at_start' added successfully.")
        except sqlite3.OperationalError as e:
            print(f"⚠️ Note: {e} (Column might already exist or table is locked)")

        # Add females_at_start
        try:
            cursor.execute("ALTER TABLE daily_log ADD COLUMN females_at_start INTEGER;")
            print("✅ Column 'females_at_start' added successfully.")
        except sqlite3.OperationalError as e:
            print(f"⚠️ Note: {e} (Column might already exist or table is locked)")

        conn.commit()
    except sqlite3.OperationalError as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    patch_db()
