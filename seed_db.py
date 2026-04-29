from app import create_app
from app.database import db
from app.services.seed_service import init_users

app = create_app()

with app.app_context():
    init_users()
