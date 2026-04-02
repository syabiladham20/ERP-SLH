import sqlite3

def drop_feed_columns(db_file='instance/farm.db'):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    try:
        # Check if columns exist before dropping to avoid errors if already dropped
        cursor.execute("PRAGMA table_info(daily_log)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'feed_male' in columns:
            print("Dropping feed_male column")
            cursor.execute("ALTER TABLE daily_log DROP COLUMN feed_male")

        if 'feed_female' in columns:
            print("Dropping feed_female column")
            cursor.execute("ALTER TABLE daily_log DROP COLUMN feed_female")

        conn.commit()
        print("Done.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    drop_feed_columns()
