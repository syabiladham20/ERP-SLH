from app import app, db, FeedCode
from sqlalchemy import text

def migrate():
    with app.app_context():
        print("Starting migration v5...")

        # 1. Create missing tables (e.g. feed_code if it doesn't exist)
        try:
            db.create_all()
            print("Ensured all tables exist (db.create_all).")
        except Exception as e:
            print(f"Error during db.create_all(): {e}")

        # 2. Populate FeedCode if empty
        try:
            if FeedCode.query.count() == 0:
                print("Populating default Feed Codes...")
                default_codes = ['161C', '162C', '163C', '168C', '169C', '170P', '171P', '172P']
                for c in default_codes:
                    db.session.add(FeedCode(code=c))
                db.session.commit()
                print("Feed Codes populated.")
            else:
                print("Feed Codes already exist.")
        except Exception as e:
             print(f"Error checking/populating FeedCode: {e}")

        # 3. Add columns to daily_log
        # We use db.engine.connect() to ensure we have a valid connection for raw SQL
        with db.engine.connect() as conn:
            def check_and_add_column(table, col, col_type):
                try:
                    # check if column exists
                    conn.execute(text(f"SELECT {col} FROM {table} LIMIT 1"))
                    print(f"Column {col} already exists in {table}.")
                except Exception:
                    print(f"Adding column {col} to {table}...")
                    try:
                        # SQLite supports ADD COLUMN
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                        conn.commit()
                        print(f"Successfully added {col}.")
                    except Exception as e:
                        print(f"Failed to add {col}: {e}")

            check_and_add_column('daily_log', 'feed_code_male_id', 'INTEGER REFERENCES feed_code(id)')
            check_and_add_column('daily_log', 'feed_code_female_id', 'INTEGER REFERENCES feed_code(id)')

        print("Migration v5 complete.")

if __name__ == "__main__":
    migrate()
