from app import app, db

def migrate():
    with app.app_context():
        print("Starting migration v6 (Hatchability)...")
        try:
            db.create_all()
            print("Ensured all tables exist (db.create_all). Hatchability table should be created.")
        except Exception as e:
            print(f"Error during db.create_all(): {e}")
        print("Migration v6 complete.")

if __name__ == "__main__":
    migrate()
