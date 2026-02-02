from app import app, db
from sqlalchemy import text

def add_column_if_not_exists(table, column, type_def):
    with app.app_context():
        # SQLite checking
        conn = db.session.connection()
        try:
            # Try to select the column to see if it exists
            conn.execute(text(f"SELECT {column} FROM {table} LIMIT 1"))
            print(f"Column {column} already exists in {table}.")
        except Exception:
            # If it fails, add it
            print(f"Adding column {column} to {table}...")
            # SQLite limitations: ALTER TABLE ADD COLUMN
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {type_def}"))
                db.session.commit()
                print("Success.")
            except Exception as e:
                print(f"Failed to add column: {e}")

if __name__ == "__main__":
    # Update Flock
    add_column_if_not_exists("flock", "production_start_date", "DATE")

    # Update DailyLog
    add_column_if_not_exists("daily_log", "mortality_male_hosp", "INTEGER DEFAULT 0")
    add_column_if_not_exists("daily_log", "culls_male_hosp", "INTEGER DEFAULT 0")
    add_column_if_not_exists("daily_log", "males_moved_to_prod", "INTEGER DEFAULT 0")
    add_column_if_not_exists("daily_log", "males_moved_to_hosp", "INTEGER DEFAULT 0")

    print("Schema migration check complete.")
