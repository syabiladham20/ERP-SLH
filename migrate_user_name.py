from app import app, db
from sqlalchemy import text
import sys

def migrate_user_table():
    with app.app_context():
        try:
            # Check if name column already exists
            inspector = db.inspect(db.engine)
            columns = [c['name'] for c in inspector.get_columns('user')]

            if 'name' not in columns:
                print("Applying schema patch: ADD COLUMN 'name' to 'user' table...")
                db.session.execute(text("ALTER TABLE user ADD COLUMN name VARCHAR(100)"))
                db.session.commit()
                print("Schema patch applied successfully.")
            else:
                print("Schema patch skipped: 'name' column already exists in 'user' table.")
        except Exception as e:
            print(f"Error applying schema patch: {e}")
            db.session.rollback()
            sys.exit(1)

if __name__ == '__main__':
    migrate_user_table()
