from app import app, db
from sqlalchemy import text

def migrate():
    with app.app_context():
        print("Starting migration v7...")

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

            check_and_add_column('daily_log', 'feed_male', 'FLOAT DEFAULT 0.0')
            check_and_add_column('daily_log', 'feed_female', 'FLOAT DEFAULT 0.0')

        print("Migration v7 complete.")

if __name__ == "__main__":
    migrate()
