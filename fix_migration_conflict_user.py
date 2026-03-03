import os
from alembic.config import Config
from alembic import command
from sqlalchemy import text, inspect
import app  # To load the Flask app context

def fix_migration():
    print("Fixing migration mismatch and verifying 'theme' column...")

    with app.app.app_context():
        engine = app.db.engine

        # First check if theme column exists
        inspector = inspect(engine)
        if inspector.has_table('user'):
            columns = [col['name'] for col in inspector.get_columns('user')]

            if 'theme' not in columns:
                print("Adding missing 'theme' column to 'user' table...")
                with engine.connect() as conn:
                    # Abstracted column addition depending on dialect
                    if engine.name == 'sqlite':
                        conn.execute(text("ALTER TABLE user ADD COLUMN theme VARCHAR(50) DEFAULT 'base_modern.html'"))
                    elif engine.name == 'postgresql':
                        conn.execute(text("ALTER TABLE \"user\" ADD COLUMN theme VARCHAR(50) DEFAULT 'base_modern.html'"))
                    conn.commit()
            else:
                print("'theme' column already exists in 'user' table.")

        # Now stamp to head to tell alembic we're up to date
        print("Stamping database with the current Alembic head...")
        alembic_cfg = Config("migrations/alembic.ini")
        alembic_cfg.set_main_option("script_location", "migrations")

        # This forces the alembic_version table to match our current migration head,
        # effectively skipping any missing or orphaned hashes (like 3f08ca69aca6)
        command.stamp(alembic_cfg, "head")
        print("Successfully stamped database to head.")

    print("Migration fix complete. Your database should now match the current code and Alembic state.")

if __name__ == '__main__':
    fix_migration()
