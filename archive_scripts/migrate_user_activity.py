from app import app, db, UserActivityLog
from sqlalchemy import inspect
from sqlalchemy import text

with app.app_context():
    inspector = inspect(db.engine)
    if 'user_activity_log' not in inspector.get_table_names():
        print("Creating user_activity_log table...")
        UserActivityLog.__table__.create(db.engine)
        print("Table user_activity_log created successfully.")
    else:
        print("Table user_activity_log already exists.")
