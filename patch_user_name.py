from app import app, db
from sqlalchemy import text

with app.app_context():
    try:
        db.session.execute(text("ALTER TABLE user ADD COLUMN name VARCHAR(100)"))
        db.session.commit()
        print("Column 'name' added successfully.")
    except Exception as e:
        print(f"Error adding column: {e}")
