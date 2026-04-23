from run import app
from app.extensions import db
from app.services.seed_service import initialize_users

with app.app_context():
    db.create_all()
    initialize_users()
