import sqlite3
import os

db_path = 'instance/farm.db'

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check current version
        cursor.execute("SELECT version_num FROM alembic_version")
        current_version = cursor.fetchone()
        print(f"Current recorded version: {current_version[0] if current_version else 'None'}")

        # Update to the latest valid version in our codebase
        # Looking at migrations/versions, 103e6b03e284 is the latest one
        # (based on the previous successful migration log: 9826ee34bd8a -> 103e6b03e284)
        target_version = '103e6b03e284'

        print(f"Updating to latest valid version: {target_version}")
        cursor.execute("UPDATE alembic_version SET version_num = ?", (target_version,))
        conn.commit()
        print("Migration state fixed successfully.")

    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
    finally:
        conn.close()
else:
    print(f"Database not found at {db_path}")
