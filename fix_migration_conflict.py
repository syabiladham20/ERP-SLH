import os
from sqlalchemy import inspect, text
from app import app, db

def fix_migration():
    """
    Checks if the database is in a state where tables exist but alembic version is missing.
    If so, stamps the database to 'head'.
    Also fixes missing columns in 'global_standard' if version is stuck.
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

        # Check alembic_version
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

        # --- HOTFIX: Check for missing 'std_hatching_egg_pct' ---
        if 'global_standard' in tables:
            columns = [c['name'] for c in inspector.get_columns('global_standard')]
            if 'std_hatching_egg_pct' not in columns:
                # Only apply manual fix if version is None (about to stamp head) OR version is the merge revision
                # The merge revision is '1a2b3c4d5e6f'.
                if version_num is None or version_num == '1a2b3c4d5e6f':
                     print("Detected missing 'std_hatching_egg_pct' column. Applying hotfix...")
                     try:
                         with db.engine.connect() as conn:
                             conn.execute(text("ALTER TABLE global_standard ADD COLUMN std_hatching_egg_pct FLOAT"))
                             conn.execute(text("UPDATE global_standard SET std_hatching_egg_pct = 96.0"))
                             conn.commit()
                         print("Hotfix applied successfully.")
                     except Exception as e:
                         print(f"Error applying hotfix: {e}")
                else:
                    print(f"Missing 'std_hatching_egg_pct' but version is {version_num}. Letting upgrade handle it.")

        # --- END HOTFIX ---

        # Check for critical tables that indicate the DB is already initialized
        # 'feed_code' is the one causing the error, so it's a good indicator
        critical_table = 'feed_code'

        if critical_table in tables:
            print(f"Table '{critical_table}' found in database.")

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
