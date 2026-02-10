from app import app, db
from sqlalchemy import text
from datetime import datetime, timedelta, date

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
    # Update SamplingEvent
    add_column_if_not_exists("sampling_event", "scheduled_date", "DATE")

    # Backfill logic
    # We need to calculate the scheduled_date for existing rows based on age_week
    # Use raw SQL to avoid model dependency issues (e.g., missing columns in DB vs Model)
    with app.app_context():
        with db.engine.connect() as conn:
            try:
                # Select rows needing update
                result = conn.execute(text("""
                    SELECT s.id, s.age_week, f.intake_date
                    FROM sampling_event s
                    JOIN flock f ON s.flock_id = f.id
                    WHERE s.scheduled_date IS NULL
                """))

                rows = result.fetchall()
                count = 0

                for row in rows:
                    s_id = row[0]
                    age_week = row[1]
                    intake_date_val = row[2]

                    # Normalize to date object
                    intake_date = None
                    if isinstance(intake_date_val, str):
                        # Try common formats
                        for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S'):
                            try:
                                intake_date = datetime.strptime(intake_date_val, fmt).date()
                                break
                            except ValueError:
                                continue
                    elif isinstance(intake_date_val, datetime):
                        intake_date = intake_date_val.date()
                    elif isinstance(intake_date_val, date):
                        intake_date = intake_date_val

                    if not intake_date:
                        print(f"Skipping row {s_id}: Could not parse intake_date '{intake_date_val}'")
                        continue

                    days_offset = ((age_week - 1) * 7) + 1
                    new_date = intake_date + timedelta(days=days_offset)

                    conn.execute(
                        text("UPDATE sampling_event SET scheduled_date = :d WHERE id = :id"),
                        {"d": new_date, "id": s_id}
                    )
                    count += 1

                conn.commit()
                if count > 0:
                    print(f"Backfilled {count} SamplingEvent dates.")
                else:
                    print("No SamplingEvent dates needed backfilling.")

            except Exception as e:
                print(f"Error during backfill: {e}")
