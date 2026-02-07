import sqlite3
import os

def migrate():
    db_path = os.path.join('instance', 'farm.db')
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if columns exist
        cursor.execute("PRAGMA table_info(daily_log)")
        columns = [info[1] for info in cursor.fetchall()]

        if 'feed_code_male_id' not in columns:
            print("Adding feed_code_male_id column...")
            cursor.execute("ALTER TABLE daily_log ADD COLUMN feed_code_male_id INTEGER REFERENCES feed_code(id)")
        else:
            print("feed_code_male_id already exists.")

        if 'feed_code_female_id' not in columns:
            print("Adding feed_code_female_id column...")
            cursor.execute("ALTER TABLE daily_log ADD COLUMN feed_code_female_id INTEGER REFERENCES feed_code(id)")
        else:
            print("feed_code_female_id already exists.")

        # Copy data from feed_code_id if it exists
        if 'feed_code_id' in columns:
            print("Migrating data from feed_code_id...")
            # We copy feed_code_id to both male and female columns where they are NULL
            cursor.execute("""
                UPDATE daily_log
                SET feed_code_male_id = feed_code_id,
                    feed_code_female_id = feed_code_id
                WHERE feed_code_id IS NOT NULL
                  AND (feed_code_male_id IS NULL OR feed_code_female_id IS NULL)
            """)
            print(f"Rows updated: {cursor.rowcount}")

        conn.commit()
        print("Migration successful.")

    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
