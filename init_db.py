from app import app, db, House, init_ui_elements

def init_db():
    with app.app_context():
        # db.create_all() # Schema is now managed by Flask-Migrate
        
        # Pre-populate Houses
        if House.query.count() == 0:
            houses = ['VA1', 'VA2', 'VA3']
            for name in houses:
                db.session.add(House(name=name))
                print(f"Added House: {name}")
        
        init_ui_elements(commit=False)

        db.session.commit()
        print("Database initialized.")

if __name__ == "__main__":
    init_db()
