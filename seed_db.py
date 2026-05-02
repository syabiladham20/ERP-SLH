from app import create_app
from app.database import db
from app.services.seed_service import initialize_users

app = create_app()

with app.app_context():
    initialize_users()
