from run import app
from app import db
from app.models.models import Farm, House, Flock
from app.services.seed_service import seed_flock

with app.app_context():
    pass
