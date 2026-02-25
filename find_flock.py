from app import app, db, Flock, User, initialize_users

with app.app_context():
    db.create_all()
    initialize_users()

    # Check for flocks
    flock = Flock.query.first()
    if flock:
        print(f"Flock ID: {flock.id}")
    else:
        print("No flocks found.")
