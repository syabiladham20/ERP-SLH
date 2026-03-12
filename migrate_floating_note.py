import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'instance', 'farm.db')

def migrate():
    print(f"Connecting to database at {db_path}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("Checking if 'floating_note' table exists...")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='floating_note'")
    if not cursor.fetchone():
        print("Creating 'floating_note' table...")
        cursor.execute('''
            CREATE TABLE floating_note (
                id INTEGER NOT NULL PRIMARY KEY,
                flock_id INTEGER NOT NULL,
                chart_id VARCHAR(50) NOT NULL,
                x_value VARCHAR(50) NOT NULL,
                y_value FLOAT NOT NULL,
                content TEXT NOT NULL,
                created_at DATETIME,
                FOREIGN KEY(flock_id) REFERENCES flock (id)
            )
        ''')
        print("Table 'floating_note' created successfully.")
    else:
        print("Table 'floating_note' already exists.")

    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == '__main__':
    migrate()
