import sqlite3
import os
import sys

def main():
    # Database path
    db_path = os.path.join('instance', 'farm.db')

    if not os.path.exists(db_path):
        print(f"Error: Database file not found at {db_path}")
        sys.exit(1)

    print(f"Connecting to database at {db_path}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if 'theme' column already exists in 'user' table
    cursor.execute("PRAGMA table_info(user)")
    columns = [col[1] for col in cursor.fetchall()]

    if 'theme' in columns:
        print("Column 'theme' already exists in the 'user' table.")
    else:
        print("Adding 'theme' column to 'user' table...")
        try:
            cursor.execute("ALTER TABLE user ADD COLUMN theme VARCHAR(50) DEFAULT 'base_tabler.html'")
            conn.commit()
            print("Successfully added 'theme' column.")
        except sqlite3.OperationalError as e:
            print(f"Error adding column: {e}")
            conn.rollback()

    # Verify data integrity
    cursor.execute("SELECT id, username, theme FROM user LIMIT 5")
    rows = cursor.fetchall()
    print("\nData check (first 5 users):")
    for row in rows:
        print(f"ID: {row[0]}, Username: {row[1]}, Theme: {row[2]}")

    conn.close()

if __name__ == '__main__':
    main()
