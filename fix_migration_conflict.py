import os
from sqlalchemy import inspect, text
from app import app, db

def fix_migration():
    """
    Checks if the database is in a state where tables exist but alembic version is missing.
    If so, stamps the database to 'head'.
    """
    with app.app_context():
        # Check if database exists by trying to connect
        try:
            # Force connection
            with db.engine.connect() as conn:
                pass
        except Exception as e:
            print(f"Database connection failed: {e}")
            return

        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        # Check for critical tables that indicate the DB is already initialized
        # 'feed_code' is the one causing the error, so it's a good indicator
        critical_table = 'feed_code'

        if critical_table in tables:
            print(f"Table '{critical_table}' found in database.")

            # Check if alembic_version table exists and has content
            alembic_version_exists = 'alembic_version' in tables
            version_num = None

            if alembic_version_exists:
                try:
                    with db.engine.connect() as conn:
                        result = conn.execute(text("SELECT version_num FROM alembic_version"))
                        row = result.fetchone()
                        if row:
                            version_num = row[0]
                except Exception as e:
                    print(f"Error reading alembic_version: {e}")

            if not version_num:
                print("No Alembic migration version found, but tables exist.")
                print("Stamping database as 'head' to skip initial migration...")

                # Run flask db stamp head
                exit_code = os.system("flask db stamp head")

                if exit_code == 0:
                    print("Successfully stamped database.")
                else:
                    print("Failed to stamp database.")
            else:
                print(f"Alembic version found: {version_num}. No action needed.")
        else:
            print(f"Table '{critical_table}' not found. Assuming clean database or pending migration.")

if __name__ == "__main__":
    fix_migration()
