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
    # Update SamplingEvent
    add_column_if_not_exists("sampling_event", "scheduled_date", "DATE")

    # Backfill logic
    # We need to calculate the scheduled_date for existing rows based on age_week
    from app import SamplingEvent, Flock
    with app.app_context():
        events = SamplingEvent.query.filter(SamplingEvent.scheduled_date == None).all()
        count = 0
        from datetime import timedelta
        for e in events:
            # Logic: e.flock.intake_date + ((e.age_week - 1) * 7 + 1) days
            days_offset = ((e.age_week - 1) * 7) + 1
            e.scheduled_date = e.flock.intake_date + timedelta(days=days_offset)
            count += 1
        if count > 0:
            db.session.commit()
            print(f"Backfilled {count} SamplingEvent dates.")
