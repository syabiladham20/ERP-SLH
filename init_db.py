from app import app, db, House

def init_db():
    with app.app_context():
        # db.create_all() # Schema is now managed by Flask-Migrate
        
        # Pre-populate Houses
        if House.query.count() == 0:
            houses = ['VA1', 'VA2', 'VA3']
            for name in houses:
                db.session.add(House(name=name))
                print(f"Added House: {name}")
        
        db.session.commit()
        print("Database initialized.")

if __name__ == "__main__":
    init_db()
