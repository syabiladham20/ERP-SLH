import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate
from sqlalchemy import event

# Add local directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Auto-version based on current timestamp
BUILD_TIME = datetime.now()
APP_VERSION = BUILD_TIME.strftime("%Y%m%d%H%M")
DISPLAY_DATE = BUILD_TIME.strftime("%B %d, %Y")
from analytics import analyze_health_events, calculate_feed_cleanup_duration
from sqlalchemy import text

load_dotenv()

# Constants for fast membership checks
ALLOWED_EXPORT_ROLES = frozenset(['Management', 'Farm'])
FARM_HATCHERY_ADMIN_DEPTS = frozenset(['Farm', 'Hatchery', 'Admin'])
FARM_HATCHERY_ADMIN_MGMT_DEPTS = frozenset(['Farm', 'Hatchery', 'Admin', 'Management'])
ADMIN_FARM_MGMT_ROLES = frozenset(['Admin', 'Farm', 'Management'])

INV_TX_TYPES_ALL = frozenset(['Purchase', 'Usage', 'Adjustment', 'Waste'])
INV_TX_TYPES_USAGE_WASTE = frozenset(['Usage', 'Waste'])

REARING_PHASES = frozenset(['Brooding', 'Growing', 'Pre-lay'])
EMPTY_NOTE_VALUES = frozenset(['none', 'nan'])

# Initial User Data for Seeding
INITIAL_USERS = [
    {'username': 'admin', 'password': 'admin123', 'dept': 'Admin', 'role': 'Admin'},
    {'username': 'farm_user', 'password': 'farm123', 'dept': 'Farm', 'role': 'Worker'},
    {'username': 'hatch_user', 'password': 'hatch123', 'dept': 'Hatchery', 'role': 'Worker'},
    {'username': 'manager', 'password': 'manager123', 'dept': 'Management', 'role': 'Management'}
]

# Pre-compile regex for natural sorting





app = Flask(__name__, template_folder='app/templates', static_folder='app/static')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Please log in to continue."
login_manager.login_message_category = "info"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

basedir = os.path.abspath(os.path.dirname(__file__))
database_url = os.getenv('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

basedir = os.path.abspath(os.path.dirname(__file__))

# Define human-readable labels for metrics
METRIC_LABELS = {
    'mortality_female_pct': 'Female Mortality',
    'mortality_male_pct': 'Male Mortality',
    'egg_production_pct': 'Egg Production Rate'
}

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///' + os.path.join(basedir, 'instance', 'farm.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev_key')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=31)
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)

from app.database import db
db.init_app(app)
migrate = Migrate(app, db)


















# Enable WAL Mode for SQLite
from sqlalchemy.engine import Engine


# --- Models ---

from app.models.models import (
    PushSubscription, NotificationHistory, NotificationRule, User, FeedCode,
    Farm, House, InventoryItem, InventoryTransaction, Flock, DailyLog,
    FloatingNote, ClinicalNote, DailyLogPhoto, PartitionWeight, Standard,
    GlobalStandard, SystemAuditLog, UserActivityLog, UIElement, SamplingEvent,
    Medication, Vaccine, ImportedWeeklyBenchmark, FlockGrading, Hatchability,
    AnonymousUser
)






# --- Initialization Helpers ---





# --- Error Handlers ---



# --- Routes ---




























































































# --- Inventory Routes ---

















import math






















import base64
from werkzeug.utils import secure_filename



# Ensure tables are created on startup if they don't exist
with app.app_context():
    try:
        db.create_all()
        from app.services.seed_service import init_ui_elements
        init_ui_elements(commit=True)
    except Exception as e:
        app.logger.warning(f"Error during db.create_all() or init_ui_elements(): {e}")






from app.routes.auth import register_auth_routes
from app.handlers import register_error_handlers, register_template_filters, register_context_processors, register_request_hooks
from app.routes.main import register_main_routes
from app.routes.production import register_production_routes
from app.routes.hatchery import register_hatchery_routes
from app.routes.health import register_health_routes
from app.routes.admin import register_admin_routes
from app.routes.api import register_api_routes


# Register Routes
register_auth_routes(app)
register_main_routes(app)
register_error_handlers(app)
register_template_filters(app)
register_context_processors(app)
register_request_hooks(app)

register_production_routes(app)
register_hatchery_routes(app)
register_health_routes(app)
register_admin_routes(app)
register_api_routes(app)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
