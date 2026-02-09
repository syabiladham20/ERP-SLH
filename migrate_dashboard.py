from app import app, db
from sqlalchemy import text

def run_migration():
    with app.app_context():
        # Use db.engine.connect() for SQLAlchemy 2.0+ or legacy engines
        with db.engine.connect() as conn:
            print("Migrating schema for Dashboard Features...")

            # 1. Create chart_configuration table
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS chart_configuration (
                        id INTEGER PRIMARY KEY,
                        house_id INTEGER NOT NULL REFERENCES house(id),
                        title VARCHAR(100) NOT NULL,
                        chart_type VARCHAR(20) DEFAULT 'line',
                        config_json TEXT NOT NULL,
                        is_template BOOLEAN DEFAULT 0
                    )
                """))
                print("Table 'chart_configuration' checked/created.")
            except Exception as e:
                print(f"Error creating chart_configuration: {e}")

            # 2. Create overview_configuration table
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS overview_configuration (
                        id INTEGER PRIMARY KEY,
                        house_id INTEGER NOT NULL UNIQUE REFERENCES house(id),
                        visible_metrics_json TEXT NOT NULL
                    )
                """))
                print("Table 'overview_configuration' checked/created.")
            except Exception as e:
                print(f"Error creating overview_configuration: {e}")

            conn.commit()
            print("Migration complete.")

if __name__ == "__main__":
    run_migration()
