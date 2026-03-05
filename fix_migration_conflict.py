import os
import subprocess
from sqlalchemy import inspect, text
from app import app, db

def fix_migration():
    """
    Checks if the database is in a state where tables exist but alembic version is missing,
    or if there are multiple migration heads.
    If tables exist but no version, stamps the database to 'head'.
    If there are multiple heads, merges them.
    """
    with app.app_context():
        # Check if database exists by trying to connect
        try:
            with db.engine.connect() as conn:
                pass
        except Exception as e:
            print(f"Database connection failed: {e}")
            return

        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        # 'feed_code' is an indicator that tables exist and the DB is somewhat initialized.
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
                        # There might be multiple heads
                        rows = result.fetchall()
                        if rows:
                            if len(rows) > 1:
                                print(f"Found multiple Alembic versions: {[r[0] for r in rows]}.")
                                # Try to resolve multiple heads in DB
                                print("Attempting to run `flask db merge heads`...")
                                merge_code = os.system("flask db merge heads -m 'Merge heads'")
                                if merge_code == 0:
                                    print("Successfully merged heads.")
                                else:
                                    print("Failed to merge heads automatically.")
                                return
                            else:
                                version_num = rows[0][0]
                except Exception as e:
                    print(f"Error reading alembic_version: {e}")

            if not version_num:
                print("No Alembic migration version found, but tables exist.")
                print("Stamping database as 'head' to skip initial migration...")

                exit_code = os.system("flask db stamp head")

                if exit_code == 0:
                    print("Successfully stamped database.")
                else:
                    print("Failed to stamp database.")
            else:
                print(f"Alembic version found: {version_num}. No action needed for missing version.")
        else:
            print(f"Table '{critical_table}' not found. Assuming clean database or pending migration.")

        # Finally, also check if there are multiple heads using alembic directly
        try:
            output = subprocess.check_output(["flask", "db", "heads"], text=True)
            head_count = len([line for line in output.strip().split('\n') if line.strip() and '(head)' in line])
            if head_count > 1:
                print(f"Found {head_count} migration heads. Attempting to merge...")
                merge_code = os.system("flask db merge heads -m 'Merge heads'")
                if merge_code == 0:
                    print("Successfully merged heads.")
                else:
                    print("Failed to merge heads.")
            else:
                print("Only one migration head found. No conflict.")
        except subprocess.CalledProcessError as e:
            print(f"Failed to check for multiple heads: {e}")
        except FileNotFoundError:
             print("flask db command not found.")

if __name__ == "__main__":
    fix_migration()
