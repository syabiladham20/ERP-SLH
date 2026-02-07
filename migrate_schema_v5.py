from app import app, db
from sqlalchemy import text

def run_migration():
    with app.app_context():
        conn = db.session.connection()

        print("Starting migration v5...")

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

        # 2. Add columns to daily_log
        columns_to_add = [
            ("feed_code_male_id", "INTEGER REFERENCES feed_code(id)"),
            ("feed_code_female_id", "INTEGER REFERENCES feed_code(id)")
        ]

        for col_name, col_def in columns_to_add:
            try:
                # Check if column exists
                conn.execute(text(f"SELECT {col_name} FROM daily_log LIMIT 1"))
                print(f"Column '{col_name}' already exists in 'daily_log'.")
            except Exception:
                print(f"Adding column '{col_name}' to 'daily_log'...")
                try:
                    conn.execute(text(f"ALTER TABLE daily_log ADD COLUMN {col_name} {col_def}"))
                    print(f"Column '{col_name}' added.")
                except Exception as e:
                    print(f"Error adding column '{col_name}': {e}")

        db.session.commit()
        print("Migration v5 complete.")

if __name__ == "__main__":
    run_migration()
