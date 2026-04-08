import sqlite3

try:
    conn = sqlite3.connect('instance/farm.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Standard LIMIT 1")
    columns = [description[0] for description in cursor.description]
    print(columns)
except Exception as e:
    print(f"Error: {e}")
