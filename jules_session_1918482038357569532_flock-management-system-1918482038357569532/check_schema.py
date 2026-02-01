from app import app, db
from sqlalchemy import inspect

def check_schema():
    with app.app_context():
        inspector = inspect(db.engine)
        for table in inspector.get_table_names():
            print(f"Table: {table}")
            columns = [c['name'] for c in inspector.get_columns(table)]
            print(f"Columns: {columns}")

if __name__ == "__main__":
    check_schema()
