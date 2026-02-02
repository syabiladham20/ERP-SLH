from app import app, db, House

def init_db():
    with app.app_context():
        db.create_all()
        
        # Pre-populate Houses
        houses = ['VA1', 'VA2', 'VA3']
        for name in houses:
            if not House.query.filter_by(name=name).first():
                db.session.add(House(name=name))
                print(f"Added House: {name}")
        
        db.session.commit()
        print("Database initialized.")

if __name__ == "__main__":
    init_db()
