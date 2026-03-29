import os
import sys

# Ensure local modules can be imported
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app import app, db
from sqlalchemy import text

def patch_database():
    with app.app_context():
        try:
            with db.engine.connect() as conn:
                print("Checking if 'remarks' column exists in 'daily_log' table...")

                # Check for SQLite or Postgres columns
                try:
                    conn.execute(text("SELECT remarks FROM daily_log LIMIT 1"))
                    print("'remarks' column already exists in 'daily_log'.")
                except Exception as check_err:
                    print("'remarks' column does not exist. Adding it...")

                    try:
                        conn.execute(text("ALTER TABLE daily_log ADD COLUMN remarks TEXT;"))
                        conn.commit()
                        print("Successfully added 'remarks' column to 'daily_log' table.")
                    except Exception as add_err:
                        print(f"Failed to add 'remarks' column: {add_err}")

        except Exception as e:
            print(f"Database connection or general error: {e}")

if __name__ == "__main__":
    patch_database()
