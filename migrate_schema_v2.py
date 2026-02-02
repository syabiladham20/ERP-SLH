from app import app, db, WeeklyData
from sqlalchemy import text

def add_column_if_not_exists(table, column, type_def):
    with app.app_context():
        conn = db.session.connection()
        try:
            conn.execute(text(f"SELECT {column} FROM {table} LIMIT 1"))
            print(f"Column {column} already exists in {table}.")
        except Exception:
            print(f"Adding column {column} to {table}...")
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {type_def}"))
                db.session.commit()
                print("Success.")
            except Exception as e:
                print(f"Failed to add column: {e}")

if __name__ == "__main__":
    # Update Standard
    add_column_if_not_exists("standard", "std_feed_male", "FLOAT DEFAULT 0.0")
    add_column_if_not_exists("standard", "std_feed_female", "FLOAT DEFAULT 0.0")

    # Create WeeklyData table
    with app.app_context():
        db.create_all()
        print("Ensured all tables exist (including WeeklyData).")

    print("Schema migration v2 complete.")
