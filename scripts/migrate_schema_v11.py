from app import app, db, FloatingNote
from sqlalchemy import text, inspect

def add_column_if_not_exists(table, column, type_def):
    with app.app_context():
        engine = db.engine
        inspector = inspect(engine)

        # Check if table exists
        if not inspector.has_table(table):
            print(f"Table {table} does not exist. Skipping.")
            return

        # Check if column exists
        columns = [col['name'] for col in inspector.get_columns(table)]

        if column in columns:
            print(f"Column '{column}' already exists in '{table}'.")
            return

        print(f"Adding column '{column}' to '{table}'...")
        with engine.begin() as conn:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {type_def}"))
                print(f"Successfully added '{column}'.")
            except Exception as e:
                print(f"Failed to add column '{column}': {e}")

def create_table_if_not_exists(model):
    with app.app_context():
        engine = db.engine
        inspector = inspect(engine)
        table = model.__tablename__
        if inspector.has_table(table):
             print(f"Table '{table}' already exists.")
             return
        print(f"Creating table '{table}'...")
        try:
             model.__table__.create(engine)
             print(f"Successfully created table '{table}'.")
        except Exception as e:
             print(f"Failed to create table '{table}': {e}")

if __name__ == "__main__":
    # From a035faca5735
    add_column_if_not_exists("daily_log", "males_at_start", "INTEGER")
    add_column_if_not_exists("daily_log", "females_at_start", "INTEGER")

    # From 103e6b03e284
    create_table_if_not_exists(FloatingNote)

    # Drop legacy table if needed
    with app.app_context():
        engine = db.engine
        inspector = inspect(engine)
        if inspector.has_table("weekly_data"):
            print("Dropping legacy table 'weekly_data'...")
            with engine.begin() as conn:
                try:
                    conn.execute(text("DROP TABLE weekly_data"))
                    print("Successfully dropped 'weekly_data'.")
                except Exception as e:
                    print(f"Failed to drop 'weekly_data': {e}")

    print("Schema migration v11 check complete.")
