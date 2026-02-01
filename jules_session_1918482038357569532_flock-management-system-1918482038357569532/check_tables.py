from app import app, db
from sqlalchemy import inspect

def list_tables():
    with app.app_context():
        inspector = inspect(db.engine)
        print(inspector.get_table_names())

if __name__ == "__main__":
    list_tables()
