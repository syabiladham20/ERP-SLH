from app import app, db
from sqlalchemy import text

def run_migration():
    with app.app_context():
        conn = db.session.connection()

        print("Migrating schema...")

        # 1. Create feed_code table
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS feed_code (
                    id INTEGER PRIMARY KEY,
                    code VARCHAR(50) UNIQUE NOT NULL
                )
            """))
            print("Table 'feed_code' checked/created.")
        except Exception as e:
            print(f"Error creating table: {e}")

        # 2. Add feed_code_id to daily_log
        try:
            conn.execute(text("ALTER TABLE daily_log ADD COLUMN feed_code_id INTEGER REFERENCES feed_code(id)"))
            print("Column 'feed_code_id' added to 'daily_log'.")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "no such column" not in str(e).lower():
                # SQLite error msg varies, but usually "duplicate column name"
                print(f"Column 'feed_code_id' likely already exists or other error: {e}")
            else:
                print(f"Error adding column: {e}")

        db.session.commit()
        print("Migration complete.")

if __name__ == "__main__":
    run_migration()
