import sqlite3
import random
import datetime

# Database file path
DB_PATH = 'instance/farm.db'

# Connect to the SQLite database
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Insert dummy flock grading data
try:
    cursor.execute("SELECT id FROM house LIMIT 1")
    house = cursor.fetchone()
    if house:
        house_id = house[0]

        # Add a grading report
        cursor.execute("""
            INSERT INTO flock_grading (house_id, age_week, sex, count, average_weight, uniformity, lowest_weight, highest_weight, grading_bins)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (house_id, 10, 'Male', 100, 1500.5, 90.5, 1200, 1800, '{"1200": 10, "1500": 80, "1800": 10}'))

        # Add another grading report
        cursor.execute("""
            INSERT INTO flock_grading (house_id, age_week, sex, count, average_weight, uniformity, lowest_weight, highest_weight, grading_bins)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (house_id, 10, 'Female', 100, 1400.5, 92.5, 1100, 1700, '{"1100": 5, "1400": 90, "1700": 5}'))

        # We need a daily log on weighing day to trigger the button
        # find active flock for this house
        cursor.execute("SELECT id, intake_date FROM flock WHERE house_id=? AND status='Active' LIMIT 1", (house_id,))
        flock = cursor.fetchone()
        if flock:
            flock_id = flock[0]
            intake_date = datetime.datetime.strptime(flock[1], "%Y-%m-%d")
            log_date = intake_date + datetime.timedelta(days=10 * 7) # week 10

            cursor.execute("""
                INSERT INTO daily_log (flock_id, date, is_weighing_day, body_weight_male, body_weight_female)
                VALUES (?, ?, ?, ?, ?)
            """, (flock_id, log_date.strftime("%Y-%m-%d"), 1, 1500, 1400))

        conn.commit()
        print("Dummy grading data inserted.")
    else:
        print("No houses found to insert dummy data.")
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
