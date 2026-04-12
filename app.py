from flask import Flask
from flask import render_template, request, redirect, url_for, flash, send_from_directory, session, g, jsonify
from flask_login import current_user, LoginManager, login_user, logout_user, login_required, UserMixin
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy.orm import joinedload
from sqlalchemy import or_, and_, func, event
from werkzeug.utils import secure_filename
import pytz
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
import os
import sys

# Ensure local modules can be imported
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from privacy_filter import privacy_filter
except ImportError:
    pass
try:
    from gemini_engine import GeminiEngine
    gemini_engine_instance = None
except ImportError:
    pass
import time
import requests
from dotenv import load_dotenv
import json
import pandas as pd
import calendar
import re
from functools import wraps
from metrics import METRICS_REGISTRY, calculate_metrics, enrich_flock_data, aggregate_weekly_metrics, aggregate_monthly_metrics
from pywebpush import webpush, WebPushException

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
_ns_re = re.compile('([0-9]+)')

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower()
            for text in _ns_re.split(s)]


def dept_required(required_dept):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                if request.path == url_for('login'): # Avoid loop
                    return f(*args, **kwargs)

                # Prevent duplicate flash messages
                flashes = session.get('_flashes', [])
                if not any(category == 'info' and msg == "Please log in to continue." for category, msg in flashes):
                    flash("Please log in to continue.", "info")
                return redirect(url_for('login'))

            user_dept = current_user.dept

            # Super Admin can access everything
            if user_dept == 'Admin':
                return f(*args, **kwargs)

            # Check if required_dept is a list/tuple
            if isinstance(required_dept, (list, tuple)):
                if user_dept in required_dept:
                    return f(*args, **kwargs)
            else:
                # If user matches required dept
                if user_dept == required_dept:
                    return f(*args, **kwargs)


            # If user is logged in but wrong department
            dept_str = ', '.join(required_dept) if isinstance(required_dept, (list, tuple)) else required_dept
            flash(f"Access Denied: You do not have permission to view the {dept_str} Department", "danger")

            # Redirect to their own dashboard
            if user_dept == 'Hatchery':
                return redirect(url_for('hatchery_dashboard'))
            elif user_dept == 'Farm':
                return redirect(url_for('index'))
            elif user_dept == 'Management':
                return redirect(url_for('executive_dashboard'))
            else:
                return redirect(url_for('login')) # Fallback

        return decorated_function
    return decorator


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

db = SQLAlchemy(app)
migrate = Migrate(app, db)

@app.template_filter('basename')
def basename_filter(s):
    if not s:
        return None
    return os.path.basename(str(s).replace('\\', '/'))

@app.context_processor
def inject_metadata():
    return {
        'version': APP_VERSION,
        'build_date': DISPLAY_DATE
    }

@app.template_filter('from_json')
def from_json_filter(value):
    import json
    try:
        return json.loads(value)
    except:
        return {}

@app.template_filter('date_fmt')
def date_fmt_filter(value):
    if value is None:
        return ""
    if isinstance(value, str):
        # Try parsing common formats if string
        try:
            value = datetime.strptime(value, '%Y-%m-%d')
        except ValueError:
            return value
    if isinstance(value, (datetime, date)):
        return value.strftime('%d-%b-%Y')
    return value

def round_to_whole(val):
    if val is None: return 0
    try:
        return int(float(val) + 0.5)
    except (ValueError, TypeError):
        return 0

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/sw.js')
def serve_sw():
    # Return as a Jinja template to inject the dynamic CACHE_NAME version
    response = app.make_response(render_template('sw.js', version=APP_VERSION))
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

@app.route('/api/get_standard_bw')
@login_required
def get_standard_bw():
    flock_id = request.args.get('flock_id', type=int)
    date_str = request.args.get('date')

    if not flock_id or not date_str:
        return jsonify({'error': 'Missing parameters'}), 400

    flock = db.session.get(Flock, flock_id)
    if not flock:
        return jsonify({'error': 'Flock not found'}), 404

    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400

    # Calculate exact age in weeks
    delta = (target_date - flock.intake_date).days
    if delta < 0:
        return jsonify({'error': 'Date is before intake date'}), 400

    weeks = delta // 7

    # Find standard for this week
    std = Standard.query.filter_by(week=weeks).first()

    last_log = DailyLog.query.filter(
        DailyLog.flock_id == flock_id,
        DailyLog.is_weighing_day == True,
        DailyLog.date <= target_date
    ).order_by(DailyLog.date.desc()).first()

    last_weighing_date = None
    last_weighing_week = None
    if last_log:
        last_weighing_date = last_log.date.strftime('%Y-%m-%d')
        last_weighing_week = (last_log.date - flock.intake_date).days // 7

    response_data = {
        'week': weeks,
        'std_bw_male': std.std_bw_male if std else '',
        'std_bw_female': std.std_bw_female if std else '',
        'last_weighing_date': last_weighing_date,
        'last_weighing_week': last_weighing_week
    }
    return jsonify(response_data)

@app.route('/api/version')
def get_version():
    return jsonify({'version': APP_VERSION})

@app.route('/api/subscribe', methods=['POST'])
@login_required
def subscribe():
    subscription_info = request.json.get('subscription')
    if not subscription_info:
        return jsonify({'error': 'Subscription info missing'}), 400

    user_id = current_user.id

    # Check if subscription already exists for this user
    sub_str = json.dumps(subscription_info)
    existing = PushSubscription.query.filter_by(user_id=user_id, subscription_json=sub_str).first()

    if not existing:
        new_sub = PushSubscription(user_id=user_id, subscription_json=sub_str)
        db.session.add(new_sub)
        safe_commit()

    return jsonify({'success': True}), 201

@app.route('/api/unsubscribe', methods=['POST'])
@login_required
def unsubscribe():
    subscription_info = request.json.get('subscription')
    if not subscription_info:
        return jsonify({'error': 'Subscription info missing'}), 400

    user_id = current_user.id
    sub_str = json.dumps(subscription_info)

    PushSubscription.query.filter_by(user_id=user_id, subscription_json=sub_str).delete()
    safe_commit()

    return jsonify({'success': True}), 200

@app.route('/offline')
def offline():
    return render_template('offline.html')

@app.route('/offline_mirror')
def offline_mirror():
    return render_template('offline_mirror.html')


def safe_commit():
    try:
        db.session.commit()
        return True
    except Exception as e:

        db.session.rollback()
        app.logger.error(f"Database transaction failed: {e}")
        flash("A database error occurred. Your changes have been rolled back to prevent data corruption.", "danger")
        return False



# Enable WAL Mode for SQLite
from sqlalchemy.engine import Engine

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    # Only execute PRAGMA for SQLite connections
    if type(dbapi_connection).__name__ == 'Connection' and 'sqlite3' in type(dbapi_connection).__module__:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
        except:
            pass
        cursor.close()

# --- Models ---

class PushSubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    subscription_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class NotificationHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=False)
    url = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    is_read = db.Column(db.Boolean, default=False)

    user = db.relationship('User', backref=db.backref('notifications', lazy=True, cascade="all, delete-orphan"))

class NotificationRule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    metric = db.Column(db.String(50), nullable=False) # e.g. 'mortality_female_pct'
    operator = db.Column(db.String(10), nullable=False) # '>', '<', '==', '>=', '<='
    threshold = db.Column(db.Float, nullable=False)
    is_active = db.Column(db.Boolean, default=True)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    dept = db.Column(db.String(50), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    theme = db.Column(db.String(50), default='base_tabler.html')
    farm_id = db.Column(db.Integer, nullable=True)
    name = db.Column(db.String(100), nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class FeedCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)

class Farm(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    flocks = db.relationship('Flock', backref='farm', lazy=True)

class House(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    flocks = db.relationship('Flock', backref='house', lazy=True)



class InventoryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), nullable=False) # 'Vaccine', 'Medication'
    unit = db.Column(db.String(20), nullable=False) # 'Bottle', 'Kg', 'Packet', 'Liter'
    current_stock = db.Column(db.Float, default=0.0)
    min_stock_level = db.Column(db.Float, default=0.0)
    doses_per_unit = db.Column(db.Integer, nullable=True) # For vaccines
    batch_number = db.Column(db.String(50), nullable=True)
    expiry_date = db.Column(db.Date, nullable=True)
    cost_per_unit = db.Column(db.Float, default=0.0)

    transactions = db.relationship('InventoryTransaction', backref='item', lazy=True, cascade="all, delete-orphan")
    vaccines = db.relationship('Vaccine', backref='inventory_item', lazy=True)
    medications = db.relationship('Medication', backref='inventory_item', lazy=True)

class InventoryTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey('inventory_item.id'), nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False) # 'Purchase', 'Usage', 'Adjustment', 'Waste'
    quantity = db.Column(db.Float, nullable=False)
    transaction_date = db.Column(db.Date, nullable=False, default=date.today)
    notes = db.Column(db.String(255), nullable=True)

class Flock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    house_id = db.Column(db.Integer, db.ForeignKey('house.id'), nullable=False, index=True)
    farm_id = db.Column(db.Integer, db.ForeignKey('farm.id'), nullable=False, index=True)
    flock_id = db.Column(db.String(100), unique=True, nullable=False)
    intake_date = db.Column(db.Date, nullable=False, default=date.today)
    
    # Intake Counts
    intake_male = db.Column(db.Integer, default=0)
    intake_female = db.Column(db.Integer, default=0)
    
    # DOA
    doa_male = db.Column(db.Integer, default=0)
    doa_female = db.Column(db.Integer, default=0)
    
    status = db.Column(db.String(20), default='Active', nullable=False, index=True) # 'Active' or 'Inactive'
    phase = db.Column(db.String(20), default='Rearing', nullable=False) # 'Rearing' or 'Production'

    @property
    def production_start_date(self):
        # We find the first log where egg production hit 5%
        # Use self.logs to avoid N+1 queries if already loaded
        logs = sorted(self.logs, key=lambda x: x.date) if self.logs else []
        alive_females = (self.intake_female or 0) - (self.doa_female or 0)

        for log in logs:
            # Replicate the logic from metrics.py to ensure 100% SSOT match
            alive_females -= ((log.mortality_female or 0) + (log.culls_female or 0))
            if alive_females > 0 and (log.eggs_collected or 0) > 0:
                hdp = ((log.eggs_collected or 0) / alive_females) * 100
                if hdp >= 5.0:
                    return log.date
        return None

    start_of_lay_date = db.Column(db.Date, nullable=True) # Date of First Egg (Biological Start)

    # Production Start Counts (New Baseline)
    prod_start_male = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    prod_start_female = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    prod_start_male_hosp = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    prod_start_female_hosp = db.Column(db.Integer, default=0, nullable=False, server_default='0')

    end_date = db.Column(db.Date, nullable=True)
    
    logs = db.relationship('DailyLog', backref='flock', lazy=True, cascade="all, delete-orphan")
    weekly_benchmarks = db.relationship('ImportedWeeklyBenchmark', backref='flock', lazy=True, cascade="all, delete-orphan")

class DailyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flock_id = db.Column(db.Integer, db.ForeignKey('flock.id'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    
    # Metrics
    males_at_start = db.Column(db.Integer, nullable=True)
    females_at_start = db.Column(db.Integer, nullable=True)
    mortality_male = db.Column(db.Integer, default=0, nullable=False, server_default='0') # Production Mortality
    mortality_female = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    
    mortality_male_hosp = db.Column(db.Integer, default=0, nullable=False, server_default='0') # Hospital Mortality
    culls_male_hosp = db.Column(db.Integer, default=0, nullable=False, server_default='0') # Hospital Culls

    mortality_female_hosp = db.Column(db.Integer, default=0, nullable=False, server_default='0') # Hospital Mortality
    culls_female_hosp = db.Column(db.Integer, default=0, nullable=False, server_default='0') # Hospital Culls

    culls_male = db.Column(db.Integer, default=0, nullable=False, server_default='0') # Production Culls
    culls_female = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    
    # Transfers
    males_moved_to_prod = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    males_moved_to_hosp = db.Column(db.Integer, default=0, nullable=False, server_default='0')

    females_moved_to_prod = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    females_moved_to_hosp = db.Column(db.Integer, default=0, nullable=False, server_default='0')

    feed_program = db.Column(db.String(50)) # 'Full Feed', 'Skip-a-day'
    # Feed (Grams per Bird)
    feed_male_gp_bird = db.Column(db.Float, default=0.0, nullable=False, server_default='0')
    feed_female_gp_bird = db.Column(db.Float, default=0.0, nullable=False, server_default='0')
    
    # Calculated Total Feed (Kg)

    eggs_collected = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    
    cull_eggs_jumbo = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    cull_eggs_small = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    cull_eggs_abnormal = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    cull_eggs_crack = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    
    egg_weight = db.Column(db.Float, default=0.0)
    
    # Body Weight (Split by Sex)
    body_weight_male = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    body_weight_female = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    uniformity_male = db.Column(db.Float, default=0.0, nullable=False, server_default='0')
    uniformity_female = db.Column(db.Float, default=0.0, nullable=False, server_default='0')

    # Partitions & Weighing Day
    is_weighing_day = db.Column(db.Boolean, default=False)

    bw_male_p1 = db.Column(db.Integer, default=0)
    bw_male_p2 = db.Column(db.Integer, default=0)
    unif_male_p1 = db.Column(db.Float, default=0.0)
    unif_male_p2 = db.Column(db.Float, default=0.0)

    bw_female_p1 = db.Column(db.Integer, default=0)
    bw_female_p2 = db.Column(db.Integer, default=0)
    bw_female_p3 = db.Column(db.Integer, default=0)
    bw_female_p4 = db.Column(db.Integer, default=0)
    unif_female_p1 = db.Column(db.Float, default=0.0)
    unif_female_p2 = db.Column(db.Float, default=0.0)
    unif_female_p3 = db.Column(db.Float, default=0.0)
    unif_female_p4 = db.Column(db.Float, default=0.0)

    standard_bw_male = db.Column(db.Integer, default=0)
    standard_bw_female = db.Column(db.Integer, default=0)
    
    # Water (Readings 1, 2, 3)
    water_reading_1 = db.Column(db.Integer, default=0)
    water_reading_2 = db.Column(db.Integer, default=0)
    water_reading_3 = db.Column(db.Integer, default=0)
    water_intake_calculated = db.Column(db.Float, default=0.0) # Calculated 24h intake
    
    # Lighting (Start/End Times)
    light_on_time = db.Column(db.String(10), nullable=True) # HH:MM
    light_off_time = db.Column(db.String(10), nullable=True) # HH:MM
    
    # Feed Cleanup (Start/End Times)
    feed_cleanup_start = db.Column(db.String(10), nullable=True) # HH:MM
    feed_cleanup_end = db.Column(db.String(10), nullable=True) # HH:MM
    
    clinical_notes = db.Column(db.Text)
    remarks = db.Column(db.Text)
    # photo_path removed, use relation 'photos'
    flushing = db.Column(db.Boolean, default=False)
    selection_done = db.Column(db.Boolean, default=False)
    spiking = db.Column(db.Boolean, default=False)

    photos = db.relationship('DailyLogPhoto', backref='log', lazy=True, cascade="all, delete-orphan")
    clinical_notes_list = db.relationship('ClinicalNote', backref='log', lazy=True, cascade="all, delete-orphan")

    # Feed Codes (Main Branch Logic)
    feed_code_male_id = db.Column(db.Integer, db.ForeignKey('feed_code.id'), nullable=True)
    feed_code_female_id = db.Column(db.Integer, db.ForeignKey('feed_code.id'), nullable=True)

    feed_code_male = db.relationship('FeedCode', foreign_keys=[feed_code_male_id], backref='male_logs')
    feed_code_female = db.relationship('FeedCode', foreign_keys=[feed_code_female_id], backref='female_logs')

    partition_weights = db.relationship('PartitionWeight', backref='log', lazy=True, cascade="all, delete-orphan")

    @property
    def age_week_day(self):
        delta = (self.date - self.flock.intake_date).days
        if delta == 0:
            return "0.0"
        elif delta > 0:
            weeks = ((delta - 1) // 7) + 1
            days = ((delta - 1) % 7) + 1
            return f"{weeks}.{days}"
        else:
            return "0.0"

class FloatingNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flock_id = db.Column(db.Integer, db.ForeignKey('flock.id'), nullable=False)
    chart_id = db.Column(db.String(50), nullable=False) # e.g. 'generalChart', 'waterChart'
    x_value = db.Column(db.String(50), nullable=False) # X-axis date string or value
    y_value = db.Column(db.Float, nullable=False) # Y-axis value
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ClinicalNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    log_id = db.Column(db.Integer, db.ForeignKey('daily_log.id'), nullable=False)
    caption = db.Column(db.String(255))
    photos = db.relationship('DailyLogPhoto', backref='note', lazy=True)

class DailyLogPhoto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    log_id = db.Column(db.Integer, db.ForeignKey('daily_log.id'), nullable=False, index=True)
    note_id = db.Column(db.Integer, db.ForeignKey('clinical_note.id'), nullable=True)
    file_path = db.Column(db.String(200), nullable=False)
    original_filename = db.Column(db.String(200), nullable=True)

class PartitionWeight(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    log_id = db.Column(db.Integer, db.ForeignKey('daily_log.id'), nullable=False)
    partition_name = db.Column(db.String(10), nullable=False) # F1, F2, F3, F4, M1, M2
    body_weight = db.Column(db.Integer, default=0)
    uniformity = db.Column(db.Float, default=0.0)

class Standard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    week = db.Column(db.Integer, unique=True, nullable=False)
    std_mortality_male = db.Column(db.Float, default=0.0)
    std_mortality_female = db.Column(db.Float, default=0.0)
    std_bw_male = db.Column(db.Integer, default=0)
    std_bw_female = db.Column(db.Integer, default=0)
    std_egg_prod = db.Column(db.Float, default=0.0)
    std_feed_male = db.Column(db.Float, default=0.0)
    std_feed_female = db.Column(db.Float, default=0.0)
    std_egg_weight = db.Column(db.Float, default=0.0)
    std_hatchability = db.Column(db.Float, default=0.0)
    std_hatching_egg_pct = db.Column(db.Float, default=0.0)
    production_week = db.Column(db.Integer, nullable=True) # Production Week 1, 2, 3...

    std_cum_eggs_hha = db.Column(db.Float, default=0.0) # Cumulative HHA (Total Eggs)
    std_cum_hatching_eggs_hha = db.Column(db.Float, default=0.0) # Cumulative HHA (Hatching Eggs)
    std_cum_chicks_hha = db.Column(db.Float, default=0.0) # Cumulative HHA (Chicks)

class GlobalStandard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    std_mortality_daily = db.Column(db.Float, default=0.05)
    std_mortality_weekly = db.Column(db.Float, default=0.3)
    std_hatching_egg_pct = db.Column(db.Float, default=96.0)
    login_required = db.Column(db.Boolean, default=True) # TEMPORARY FEATURE

class SystemAuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    module = db.Column(db.String(100), nullable=False)
    action = db.Column(db.String(255), nullable=False)
    performance_impact = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True)

class UserActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    action = db.Column(db.String(50), nullable=False) # e.g., 'Add', 'Edit', 'Delete', 'Save'
    resource_type = db.Column(db.String(50), nullable=False) # e.g., 'Flock', 'DailyLog'
    resource_id = db.Column(db.String(100), nullable=True) # ID or name of the resource
    details = db.Column(db.Text, nullable=True) # JSON string of changes

    user = db.relationship('User', backref=db.backref('activity_logs', lazy=True, cascade="all, delete-orphan"))

def log_user_activity(user_id, action, resource_type, resource_id=None, details=None):
    """
    Globally log user activities safely without interrupting the main transaction.
    """
    if not user_id:
        return
    try:
        # Wrap in a nested try-except block so if it fails, it doesn't block the caller.
        details_str = json.dumps(details) if details else None
        log = UserActivityLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            details=details_str
        )
        # Avoid flushing or committing the main transaction prematurely.
        # Just add it to the session; it will commit when the route commits.
        with db.session.no_autoflush:
            db.session.add(log)
    except Exception as e:
        app.logger.warning(f"Failed to create UserActivityLog: {e}")

class UIElement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    label = db.Column(db.String(100), nullable=False)
    section = db.Column(db.String(50), nullable=False) # 'navbar_main', 'navbar_health', 'flock_card', 'flock_detail'
    is_visible = db.Column(db.Boolean, default=True)
    order_index = db.Column(db.Integer, default=0)

class SamplingEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flock_id = db.Column(db.Integer, db.ForeignKey('flock.id'), nullable=False)
    flock = db.relationship('Flock', backref=db.backref('sampling_events', cascade="all, delete-orphan"))
    age_week = db.Column(db.Integer, nullable=False)
    test_type = db.Column(db.String(50), nullable=False) # 'Serology', 'Salmonella', 'Serology & Salmonella'
    status = db.Column(db.String(20), default='Pending') # 'Pending', 'Completed'
    result_file = db.Column(db.String(200), nullable=True) # Path to PDF
    upload_date = db.Column(db.Date, nullable=True)
    actual_date = db.Column(db.Date, nullable=True)
    remarks = db.Column(db.String(255), nullable=True)
    scheduled_date = db.Column(db.Date, nullable=True)

class Medication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flock_id = db.Column(db.Integer, db.ForeignKey('flock.id'), nullable=False)
    drug_name = db.Column(db.String(100), nullable=False)
    dosage = db.Column(db.String(50), nullable=False)
    amount_used = db.Column(db.String(100), nullable=True)
    amount_used_qty = db.Column(db.Float, nullable=True)
    withdrawal_period_days = db.Column(db.Integer, default=0)
    start_date = db.Column(db.Date, nullable=False, default=date.today)
    end_date = db.Column(db.Date, nullable=True)
    remarks = db.Column(db.String(255), nullable=True)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey('inventory_item.id'), nullable=True)

    flock = db.relationship('Flock', backref=db.backref('medications', lazy=True, cascade="all, delete-orphan"))

class Vaccine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flock_id = db.Column(db.Integer, db.ForeignKey('flock.id'), nullable=False)
    # Age can be defined by Day (for first few weeks) or Week
    age_code = db.Column(db.String(10), nullable=False) # 'D1', 'W6', etc.
    vaccine_name = db.Column(db.String(200), nullable=False)
    route = db.Column(db.String(50), nullable=True)

    # Dates
    est_date = db.Column(db.Date, nullable=True)
    actual_date = db.Column(db.Date, nullable=True)
    remarks = db.Column(db.String(255), nullable=True)
    doses_per_unit = db.Column(db.Integer, default=1000)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey('inventory_item.id'), nullable=True)

    flock = db.relationship('Flock', backref=db.backref('vaccines', lazy=True, cascade="all, delete-orphan"))

    def get_live_stock(self):
        # Fallback query if not provided
        if not self.flock: return 0
        if not self.est_date: return self.flock.intake_female + self.flock.intake_male

        # Determine live stock at est_date
        # Intake - (Mortality + Culls up to est_date - 1)
        # Actually, "at time of vaccination" -> Start of Day of est_date.

        # This query is slow inside loops, use enrichment where possible.
        stmt = db.session.query(
            db.func.sum(DailyLog.mortality_male),
            db.func.sum(DailyLog.mortality_female),
            db.func.sum(DailyLog.culls_male),
            db.func.sum(DailyLog.culls_female)
        ).filter(DailyLog.flock_id == self.flock_id, DailyLog.date < self.est_date).first()

        mort_m = stmt[0] or 0
        mort_f = stmt[1] or 0
        cull_m = stmt[2] or 0
        cull_f = stmt[3] or 0

        current_stock = (self.flock.intake_male + self.flock.intake_female) - (mort_m + mort_f + cull_m + cull_f)
        return max(0, current_stock)

    def dose_count(self, live_stock=None):
        if live_stock is None:
            live_stock = self.get_live_stock()

        dpu = self.doses_per_unit
        if self.inventory_item and self.inventory_item.doses_per_unit:
             dpu = self.inventory_item.doses_per_unit

        unit_size = dpu if dpu > 0 else 1000
        import math
        units = math.ceil(live_stock / unit_size)
        return units * unit_size

    def units_needed(self, live_stock=None):
        if live_stock is None:
            live_stock = self.get_live_stock()

        dpu = self.doses_per_unit
        if self.inventory_item and self.inventory_item.doses_per_unit:
             dpu = self.inventory_item.doses_per_unit

        unit_size = dpu if dpu > 0 else 1000
        import math
        return math.ceil(live_stock / unit_size)

class ImportedWeeklyBenchmark(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flock_id = db.Column(db.Integer, db.ForeignKey('flock.id'), nullable=False)
    week = db.Column(db.Integer, nullable=False)

    mortality_male = db.Column(db.Integer, default=0)
    mortality_female = db.Column(db.Integer, default=0)
    eggs_collected = db.Column(db.Integer, default=0)
    bw_male = db.Column(db.Integer, default=0)
    bw_female = db.Column(db.Integer, default=0)

class FlockGrading(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    house_id = db.Column(db.Integer, db.ForeignKey('house.id'), nullable=False, index=True)
    age_week = db.Column(db.Integer, nullable=False)
    sex = db.Column(db.String(10), nullable=False) # 'Male' or 'Female'

    # Statistics
    count = db.Column(db.Integer, default=0)
    average_weight = db.Column(db.Float, default=0.0)
    uniformity = db.Column(db.Float, default=0.0)

    # Limits
    lowest_weight = db.Column(db.Float, default=0.0)
    highest_weight = db.Column(db.Float, default=0.0)

    # Bins Mapping in JSON
    grading_bins = db.Column(db.Text, nullable=True) # e.g. '{"700": 5, "800": 10}'

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Hatchability(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flock_id = db.Column(db.Integer, db.ForeignKey('flock.id'), nullable=False)
    setting_date = db.Column(db.Date, nullable=False)
    candling_date = db.Column(db.Date, nullable=False)
    hatching_date = db.Column(db.Date, nullable=False)

    egg_set = db.Column(db.Integer, default=0)
    clear_eggs = db.Column(db.Integer, default=0) # Infertile
    rotten_eggs = db.Column(db.Integer, default=0) # Contaminated
    hatched_chicks = db.Column(db.Integer, default=0) # Total Hatched

    male_ratio_pct = db.Column(db.Float, nullable=True) # Optional

    flock = db.relationship('Flock', backref=db.backref('hatchability_data', lazy=True, cascade="all, delete-orphan"))

    @property
    def hatchable_eggs(self):
        return self.egg_set - self.clear_eggs - self.rotten_eggs

    @property
    def hatchability_pct(self):
        # Hatch of Total
        return (self.hatched_chicks / self.egg_set * 100) if self.egg_set > 0 else 0.0

    @property
    def fertile_egg_pct(self):
        # Hatchable / Egg Set (or Fertility %)
        return (self.hatchable_eggs / self.egg_set * 100) if self.egg_set > 0 else 0.0

    @property
    def clear_egg_pct(self):
        return (self.clear_eggs / self.egg_set * 100) if self.egg_set > 0 else 0.0

    @property
    def rotten_egg_pct(self):
        return (self.rotten_eggs / self.egg_set * 100) if self.egg_set > 0 else 0.0

def get_flock_stock_history(flock_id):
    """
    Returns a dictionary mapping date -> live_stock (start of day).
    Useful for batch processing vaccines without N+1 queries.
    """
    flock = Flock.query.get(flock_id)
    if not flock: return {}

    logs = DailyLog.query.filter_by(flock_id=flock_id).order_by(DailyLog.date.asc()).all()

    stock_map = {}
    current_stock = flock.intake_male + flock.intake_female

    # We assume logs are contiguous or we handle gaps by carrying forward?
    # Actually, we need stock AT any date.
    # If we iterate logs, we get stock at Log Date.
    # We can build a cumulative mortality map.

    cum_loss = 0
    # Map from Date -> Cumulative Loss BEFORE that date (Start of Day)

    for log in logs:
        stock_map[log.date] = max(0, (flock.intake_male + flock.intake_female) - cum_loss)
        cum_loss += (log.mortality_male + log.mortality_female + log.culls_male + log.culls_female)

    # Also add "today/future" if needed, but mostly we query by log dates or est_dates.
    # If est_date is in future beyond logs, use last known stock.
    stock_map['latest'] = max(0, (flock.intake_male + flock.intake_female) - cum_loss)

    return stock_map

def get_flock_stock_history_bulk(flocks):
    """
    Returns a dictionary mapping flock_id -> {date -> live_stock (start of day)}.
    Optimized for bulk processing.
    """
    if not flocks: return {}

    flock_ids = [f.id for f in flocks]

    # Fetch all logs in one query
    logs = DailyLog.query.filter(DailyLog.flock_id.in_(flock_ids)).order_by(DailyLog.flock_id, DailyLog.date.asc()).all()

    # Group logs by flock
    logs_by_flock = {}
    for log in logs:
        if log.flock_id not in logs_by_flock:
            logs_by_flock[log.flock_id] = []
        logs_by_flock[log.flock_id].append(log)

    result_map = {}

    for f in flocks:
        f_id = f.id
        stock_map = {}
        cum_loss = 0

        # Get logs for this flock
        f_logs = logs_by_flock.get(f_id, [])

        # Calculate stock history
        for log in f_logs:
            stock_map[log.date] = max(0, (f.intake_male + f.intake_female) - cum_loss)
            cum_loss += (log.mortality_male + log.mortality_female + log.culls_male + log.culls_female)

        # Add "latest" entry
        stock_map['latest'] = max(0, (f.intake_male + f.intake_female) - cum_loss)
        result_map[f_id] = stock_map

    return result_map

def calculate_male_ratio(flock_id, setting_date, flock_obj=None, logs=None, last_hatch_date=None, hatchery_records=None):
    flock = flock_obj or db.session.get(Flock, flock_id)
    if not flock: return None, False

    weekday = setting_date.weekday() # Mon=0, Tue=1 ... Fri=4

    start_date = None
    end_date = setting_date - timedelta(days=1)

    large_window = False

    if weekday == 1: # Tuesday -> Fri, Sat, Sun, Mon (4 days)
        start_date = setting_date - timedelta(days=4)
    elif weekday == 4: # Friday -> Tue, Wed, Thu (3 days)
        start_date = setting_date - timedelta(days=3)
    else:
        # Non-Standard
        if last_hatch_date:
            start_date = last_hatch_date
        else:
            if hatchery_records is not None:
                # Use cached hatchery_records (assumed sorted or at least we can just find the latest one before setting_date)
                last_hatch = None
                # Sort descending to find the first one before setting_date
                sorted_records = sorted(hatchery_records, key=lambda x: x.setting_date, reverse=True)
                for rec in sorted_records:
                    if rec.setting_date < setting_date:
                        last_hatch = rec
                        break
            else:
                # Find LAST setting date for this flock BEFORE current setting_date from DB
                last_hatch = Hatchability.query.filter_by(flock_id=flock_id)\
                    .filter(Hatchability.setting_date < setting_date)\
                    .order_by(Hatchability.setting_date.desc()).first()

            if last_hatch:
                start_date = last_hatch.setting_date
            else:
                # First time catch
                start_date = setting_date - timedelta(days=7)

    days_count = (end_date - start_date).days + 1
    if days_count > 10:
        large_window = True

    # Calculate ratios daily
    if logs is None:
        logs = DailyLog.query.filter_by(flock_id=flock_id).order_by(DailyLog.date).all()

    # Init stocks (Production)
    curr_m_prod = flock.intake_male or 0
    curr_f_prod = flock.intake_female or 0
    curr_m_hosp = 0
    curr_f_hosp = 0

    prod_start_date = flock.production_start_date
    in_prod = False

    ratios = []

    for log in logs:
        # Check Phase Switch (Reset Baseline)
        if not in_prod:
             if prod_start_date and log.date >= prod_start_date:
                 in_prod = True
                 if (flock.prod_start_male or 0) > 0 or (flock.prod_start_female or 0) > 0:
                     curr_m_prod = flock.prod_start_male or 0
                     curr_f_prod = flock.prod_start_female or 0
                     curr_m_hosp = flock.prod_start_male_hosp or 0
                     curr_f_hosp = flock.prod_start_female_hosp or 0

        # Determine Ratio for this date (Start of Day)
        # Use Prod Stocks
        if start_date <= log.date <= end_date:
             if curr_f_prod > 0:
                 r = (curr_m_prod / curr_f_prod) * 100
                 ratios.append(r)

        # Update Stocks (End of Day)
        # Male
        mort_m_prod = log.mortality_male or 0
        mort_m_hosp = log.mortality_male_hosp or 0
        cull_m_prod = log.culls_male or 0
        cull_m_hosp = log.culls_male_hosp or 0
        moved_to_hosp_m = log.males_moved_to_hosp or 0
        moved_to_prod_m = log.males_moved_to_prod or 0

        curr_m_prod = curr_m_prod - mort_m_prod - cull_m_prod - moved_to_hosp_m + moved_to_prod_m
        curr_m_hosp = curr_m_hosp - mort_m_hosp - cull_m_hosp + moved_to_hosp_m - moved_to_prod_m

        # Female
        mort_f_prod = log.mortality_female or 0
        mort_f_hosp = log.mortality_female_hosp or 0
        cull_f_prod = log.culls_female or 0
        cull_f_hosp = log.culls_female_hosp or 0
        moved_to_hosp_f = log.females_moved_to_hosp or 0
        moved_to_prod_f = log.females_moved_to_prod or 0

        curr_f_prod = curr_f_prod - mort_f_prod - cull_f_prod - moved_to_hosp_f + moved_to_prod_f
        curr_f_hosp = curr_f_hosp - mort_f_hosp - cull_f_hosp + moved_to_hosp_f - moved_to_prod_f

        if curr_m_prod < 0: curr_m_prod = 0
        if curr_f_prod < 0: curr_f_prod = 0
        if curr_m_hosp < 0: curr_m_hosp = 0
        if curr_f_hosp < 0: curr_f_hosp = 0

    if not ratios:
        return None, large_window

    avg = sum(ratios) / len(ratios)
    return avg, large_window

# --- Initialization Helpers ---

def init_ui_elements(commit=True):
    default_elements = [
        # Navbar Main
        {'key': 'nav_dashboard', 'label': 'Dashboard', 'section': 'navbar_main', 'order': 1},
        {'key': 'nav_daily_entry', 'label': 'Daily Entry', 'section': 'navbar_main', 'order': 2},
        {'key': 'nav_health_log', 'label': 'Health Log', 'section': 'navbar_main', 'order': 3},
        {'key': 'nav_inventory', 'label': 'Inventory', 'section': 'navbar_main', 'order': 4},

        # Navbar Health Dropdown
        {'key': 'nav_health_vaccine', 'label': 'Vaccine', 'section': 'navbar_health', 'order': 1},
        {'key': 'nav_health_sampling', 'label': 'Sampling', 'section': 'navbar_health', 'order': 2},
        {'key': 'nav_health_medication', 'label': 'Medication', 'section': 'navbar_health', 'order': 3},
        {'key': 'nav_health_notes', 'label': 'Post Mortem', 'section': 'navbar_health', 'order': 4},
        {'key': 'nav_weight_grading', 'label': 'Bodyweight', 'section': 'navbar_health', 'order': 5},

        # Flock Card (Dashboard)
        {'key': 'card_details', 'label': 'See Details', 'section': 'flock_card', 'order': 1},
        {'key': 'card_start_prod', 'label': 'Start Prod', 'section': 'flock_card', 'order': 2},

        # Flock Detail (Overview Footer)
        {'key': 'detail_kpi', 'label': 'KPI Dashboard', 'section': 'flock_detail', 'order': 1},
        {'key': 'detail_custom', 'label': 'Custom Dashboard', 'section': 'flock_detail', 'order': 2},
        {'key': 'detail_charts', 'label': 'Advanced Charts', 'section': 'flock_detail', 'order': 3},
        {'key': 'detail_hatch', 'label': 'Hatchability', 'section': 'flock_detail', 'order': 4},
        {'key': 'detail_health', 'label': 'Health Log', 'section': 'flock_detail', 'order': 5},
    ]

    # Bulk fetch existing elements to avoid N+1 queries
    existing_elements = {e.key: e for e in UIElement.query.all()}

    for elem in default_elements:
        if elem['key'] not in existing_elements:
            new_elem = UIElement(
                key=elem['key'],
                label=elem['label'],
                section=elem['section'],
                order_index=elem['order']
            )
            db.session.add(new_elem)
        else:
            # Update existing element properties if they differ
            existing = existing_elements[elem['key']]
            if existing.label != elem['label'] or existing.section != elem['section'] or existing.order_index != elem['order']:
                existing.label = elem['label']
                existing.section = elem['section']
                existing.order_index = elem['order']

    if commit:
        safe_commit()
    else:
        db.session.flush()

def initialize_sampling_schedule(flock_id, commit=True):
    # Updated Schedule based on user input
    schedule = {
        1: 'Serology & Salmonella',
        4: 'Salmonella',
        8: 'Serology',
        16: 'Salmonella',
        18: 'Serology',
        24: 'Serology',
        28: 'Salmonella',
        30: 'Serology',
        38: 'Serology',
        40: 'Salmonella',
        50: 'Serology',
        52: 'Salmonella',
        58: 'Serology',
        64: 'Salmonella',
        70: 'Serology',
        76: 'Salmonella',
        90: 'Salmonella'
    }

    # Check if already initialized to avoid duplicates
    existing = SamplingEvent.query.filter_by(flock_id=flock_id).first()
    if existing:
        return

    flock = Flock.query.get(flock_id)
    if not flock: return

    for week, test in schedule.items():
        days_offset = ((week - 1) * 7) + 1
        scheduled_date = flock.intake_date + timedelta(days=days_offset)

        event = SamplingEvent(
            flock_id=flock_id,
            age_week=week,
            test_type=test,
            status='Pending',
            scheduled_date=scheduled_date
        )
        db.session.add(event)

    if commit:
        safe_commit()
    else:
        db.session.flush()

def initialize_users():
    # Helper to seed users if table is empty or missing specific users
    for u_data in INITIAL_USERS:
        user = User.query.filter_by(username=u_data['username']).first()
        if not user:
            user = User(
                username=u_data['username'],
                dept=u_data['dept'],
                role=u_data['role']
            )
            user.set_password(u_data['password'])
            db.session.add(user)
    safe_commit()

def initialize_vaccine_schedule(flock_id, commit=True):
    flock = Flock.query.get(flock_id)
    if not flock: return

    schedule_data = [
        ('D1', 'TRIVALENT VAXXITEK', 'S/C'),
        ('D1', 'PREVEXXION', 'S/C'),
        ('D1', 'COCCIVAC', 'SPRAY'),
        ('D1', 'MA5 CLONE 30', 'SPRAY'),
        ('D1', 'IBIRD', 'SPRAY'),
        ('D8', 'REO S1133', 'S/C'),
        ('D8', 'MA5 CLONE 30', 'EYE DROP'),
        ('D14', 'NEW LS MASS (RHONE MA)', 'EYE DROP'),
        ('D21', 'MA5 CLONE 30', 'EYE DROP'),
        ('D21', 'VECTORMUNE FP-MG', 'W/W'),
        ('D28', 'ND STANDARD (0.2ml)', 'EYE DROP'),
        ('W6', 'FC OIL (0.2ml)', 'I/M'),
        ('W7', 'ANIVAC H9N2', 'I/M'),
        ('W7', 'NOBILIS IB 4/91 + MA5 CLONE 30', 'EYE DROP'),
        ('W8', 'ND STANDARD (0.4ml)', 'I/M'),
        ('W9', 'LT IVAX', 'EYE DROP'),
        ('W9', 'ANIVAC FADV', 'I/M'),
        ('W10', 'CEVA CIRCOMUNE', 'W/W'),
        ('W10', 'POXIMUNE AE', 'W/W'),
        ('W12', 'REO S1133', 'S/C'),
        ('W12', 'MS VAC', 'I/M'),
        ('W12', 'NEMOVAC', 'D/W'),
        ('W13', 'CORYZA GEL 3', 'I/M'),
        ('W13', 'GALLIVAC LASOTA IB MASS', 'EYE DROP'),
        ('W14', 'GALLIMUNE 407', 'I/M'),
        ('W14', 'ANIVAC H9N2', 'I/M'),
        ('W16', 'GALLIVAC LASOTA IB MASS', 'D/W'),
        ('W17', 'NOBILIS IB 4/91 + MA5 CLONE 30', 'EYE DROP'),
        ('W17', 'FC OIL', 'I/M'),
        ('W18', 'NOBILIS REO+IB+G+ND', 'I/M'),
        ('W18', 'CORYZA OIL 3', 'I/M'),
        ('W19', 'ANIVAC FADV', 'I/M'),
        ('W19', 'MG BAC', 'I/M'),
        ('W20', 'NEW LS MASS (RHONE MA)', 'D/W'),
        ('W21', 'MS VAC', 'I/M'),
        ('W22', 'NEW LS MASS (RHONE MA)', 'D/W'),
        ('W23', 'ANIVAC H9N2', 'I/M'),
        ('W28', 'GALLIVAC LASOTA IB MASS', 'D/W'),
        ('W32', 'CEVAC NBL', 'D/W'),
        ('W32', 'IBIRD', 'D/W'),
        ('W36', 'NEW LS MASS (RHONE MA)', 'D/W'),
        ('W40', 'GALLIVAC LASOTA IB MASS', 'D/W'),
        ('W44', 'CEVAC NBL', 'D/W'),
        ('W44', 'IBIRD', 'D/W'),
        ('W48', 'NEW LS MASS (RHONE MA)', 'D/W'),
        ('W52', 'GALLIVAC LASOTA IB MASS', 'D/W'),
        ('W56', 'CEVAC NBL', 'D/W'),
        ('W56', 'IBIRD', 'D/W'),
    ]

    for age_code, vaccine, route in schedule_data:
        offset = 0
        if age_code.startswith('D'):
            try:
                days = int(age_code[1:])
                offset = days
            except: pass
        elif age_code.startswith('W'):
            try:
                weeks = int(age_code[1:])
                offset = (weeks - 1) * 7 + 1
            except: pass

        est_date = flock.intake_date + timedelta(days=offset)

        v = Vaccine(
            flock_id=flock_id,
            age_code=age_code,
            vaccine_name=vaccine,
            route=route,
            est_date=est_date
        )
        db.session.add(v)

    if commit:
        safe_commit()
    else:
        db.session.flush()

# --- Error Handlers ---

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    import traceback
    error_details = traceback.format_exc() if app.debug else "An unexpected error occurred."
    return render_template('errors/500.html', error=error_details), 500

@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

# --- Routes ---

@app.context_processor
def inject_system_health():
    logs = []
    try:
        logs = SystemAuditLog.query.order_by(SystemAuditLog.timestamp.desc()).limit(3).all()
    except Exception:
        pass

    return dict(system_health_logs=logs)

@app.before_request
def load_logged_in_user():
    # Keep the global variables set based on current_user
    if current_user.is_authenticated:
        session['user_id'] = current_user.id
        session['user_name'] = current_user.username
        session['user_dept'] = current_user.dept
        session['user_role'] = current_user.role
        session['is_admin'] = (current_user.role == 'Admin')

    # TEMPORARY FEATURE: Auto-login if login_required is False
    login_not_required = False
    try:
        gs = GlobalStandard.query.first()
        if gs and hasattr(gs, 'login_required') and not gs.login_required:
            login_not_required = True
    except Exception:
        pass # Table might not exist yet during initial setup/migration

    if login_not_required and not current_user.is_authenticated:
        # Auto-login as Admin
        admin = User.query.filter_by(role='Admin').first()
        if not admin:
             # Fallback to username 'admin'
             admin = User.query.filter_by(username='admin').first()

        if admin:
            login_user(admin)
            session['user_id'] = admin.id
            session['user_name'] = admin.username
            session['user_dept'] = admin.dept
            session['user_role'] = admin.role
            session['is_admin'] = (admin.role == 'Admin')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session.clear()
            login_user(user, remember=remember)
            session['user_id'] = user.id
            session['user_name'] = user.username
            session['user_dept'] = user.dept
            session['user_role'] = user.role
            session['is_admin'] = (user.role == 'Admin')

            if remember:
                session.permanent = True
            else:
                session.permanent = False

            flash(f"Welcome back, {user.username}!", "success")

            if user.dept == 'Hatchery':
                return redirect(url_for('hatchery_dashboard'))
            elif user.dept == 'Admin':
                return redirect(url_for('index'))
            elif user.dept == 'Management':
                return redirect(url_for('executive_dashboard'))
            else:
                return redirect(url_for('index'))
        else:
            flash("Invalid username or password.", "danger")

    return render_template('login_modern.html')

@app.route('/logout')
def logout():
    session.clear()
    logout_user()
    flash("You have been logged out.", "info")

    # Render a small intermediate page to clear localStorage, then redirect to login
    response = """
    <html>
        <body>
            <script>
                localStorage.removeItem("slh_offline_user_id");
                localStorage.removeItem("slh_offline_user_role");
                localStorage.removeItem("slh_offline_user_dept");
                window.location.href = "%s";
            </script>
        </body>
    </html>
    """ % url_for('login')
    return response

@app.route('/settings/profile_update', methods=['POST'])
@login_required
def profile_update():
    user = User.query.get(current_user.id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('login'))

    current_password = request.form.get('current_password')
    new_name = request.form.get('name')
    new_username = request.form.get('username')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    # Phase 2: Security check - Does the password match?
    if not check_password_hash(user.password_hash, current_password):
        flash("Incorrect current password. Profile update denied.", "danger")
        return redirect(url_for('settings'))

    changed = False

    if new_username and new_username != user.username:
        # Check if username already exists
        existing_user = User.query.filter_by(username=new_username).first()
        if existing_user:
            flash("Username already taken. Please choose another.", "danger")
            return redirect(url_for('settings'))
        user.username = new_username
        changed = True

    if new_name is not None and new_name != user.name:
        user.name = new_name
        changed = True

    if new_password:
        if new_password != confirm_password:
            flash("New passwords do not match.", "danger")
            return redirect(url_for('settings'))
        user.set_password(new_password)
        changed = True

    if changed:
        if safe_commit():
            session['user_name'] = user.name or user.username
            flash("Profile updated successfully.", "success")
        else:
            flash("Database error occurred while updating profile.", "danger")
    else:
        flash("No changes were made.", "info")

    return redirect(url_for('settings'))

@app.route('/settings', methods=['GET'])
@login_required
def settings():
    user_id = current_user.id
    # Fetch notification history for the user (last 30)
    notifications = NotificationHistory.query.filter_by(user_id=user_id).order_by(NotificationHistory.created_at.desc()).limit(30).all()

    # Mark as read when viewing settings
    for n in notifications:
        if not n.is_read:
            n.is_read = True
    safe_commit()

    # Pass vapid public key
    vapid_public_key = os.getenv('VAPID_PUBLIC_KEY', '')
    if not vapid_public_key:
        flash("VAPID Keys are missing. Push notifications cannot be enabled.", "warning")

    return render_template('settings.html', vapid_public_key=vapid_public_key, notifications=notifications)

def send_push_alert(user_id, title, body, url=None, transient=False):
    # Log the notification history for the user
    if not transient:
        try:
            new_notification = NotificationHistory(
                user_id=user_id,
                title=title,
                body=body,
                url=url
            )
            db.session.add(new_notification)
            safe_commit()
        except Exception as e:
            app.logger.warning(f"Failed to log notification history: {e}")
            db.session.rollback()

    vapid_private_key = os.getenv('VAPID_PRIVATE_KEY')
    vapid_claim_email = os.getenv('VAPID_CLAIM_EMAIL')

    if not vapid_private_key or not vapid_claim_email:
        app.logger.warning("VAPID keys not configured. Cannot send push notification.")
        return False

    subscriptions = PushSubscription.query.filter_by(user_id=user_id).all()
    if not subscriptions:
        return False

    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url or '/'
    })

    success_count = 0
    for sub in subscriptions:
        try:
            sub_info = json.loads(sub.subscription_json)
            webpush(
                subscription_info=sub_info,
                data=payload,
                vapid_private_key=vapid_private_key,
                vapid_claims={"sub": vapid_claim_email}
            )
            success_count += 1
        except WebPushException as ex:
            # If subscription is no longer valid, remove it
            if hasattr(ex, 'response') and ex.response and ex.response.status_code in [403, 404, 410]:
                app.logger.debug(f"Cleaning up invalid push subscription (Status {ex.response.status_code})")
                db.session.delete(sub)
                safe_commit()
            elif hasattr(ex, 'response') and ex.response and ex.response.status_code >= 500:
                app.logger.error(f"WebPush Critical Error: {repr(ex)}")
            else:
                app.logger.error(f"WebPush Error: {repr(ex)}")
        except Exception as e:
            app.logger.error(f"Push Error: {str(e)}")

    return success_count > 0

@app.route('/api/test_notification', methods=['POST'])
@login_required
def test_notification():
    user_id = current_user.id
    # Call the push alert function
    try:
        success = send_push_alert(user_id, "Test Notification", "Your device is successfully linked!", url=url_for('index'))
        if success:
            return jsonify({'success': True, 'message': 'Notification sent successfully.'}), 200
        else:
            return jsonify({'success': False, 'message': 'No valid push subscriptions found or all failed. Please re-subscribe.'}), 400
    except Exception as e:
        app.logger.error(f"Failed to send test push: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if not current_user.id:
        return redirect(url_for('login'))

    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        user = User.query.get(session['user_id'])

        if not user or not user.check_password(current_password):
            flash("Incorrect current password.", "danger")
        elif new_password != confirm_password:
            flash("New passwords do not match.", "danger")
        else:
            user.set_password(new_password)
            safe_commit()
            flash("Password updated successfully.", "success")
            return redirect(url_for('index'))

    return render_template('change_password.html')

@app.route('/admin/audit_logs')
@login_required
def admin_audit_logs():
    if not current_user.role == 'Admin':
        flash("Access Denied.", "danger")
        return redirect(url_for('index'))
    logs = SystemAuditLog.query.order_by(SystemAuditLog.timestamp.desc()).all()
    return render_template('admin/audit_logs.html', logs=logs)

@app.route('/admin/activity_log')
def admin_activity_log():
    if not current_user.role == 'Admin':
        flash("Access Denied.", "danger")
        return redirect(url_for('index'))

    user_id = request.args.get('user_id')
    resource_type = request.args.get('resource_type')

    query = UserActivityLog.query

    if user_id:
        query = query.filter_by(user_id=user_id)
    if resource_type:
        query = query.filter_by(resource_type=resource_type)

    logs = query.order_by(UserActivityLog.timestamp.desc()).limit(200).all()
    users = User.query.order_by(User.username).all()

    # Extract unique resource types for filter dropdown
    resource_types = db.session.query(UserActivityLog.resource_type).distinct().all()
    resource_types = [r[0] for r in resource_types]

    return render_template('admin/activity_log.html', logs=logs, users=users, resource_types=resource_types)

@app.route('/admin/rules', methods=['GET', 'POST'])
def manage_rules():
    if not current_user.role == 'Admin' and current_user.role != 'Management':
        flash("Access Denied.", "danger")
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = request.form.get('name')
        metric = request.form.get('metric')
        operator = request.form.get('operator')
        threshold = float(request.form.get('threshold'))
        is_active = True if request.form.get('is_active') else False

        rule = NotificationRule(
            name=name,
            metric=metric,
            operator=operator,
            threshold=threshold,
            is_active=is_active
        )
        db.session.add(rule)
        safe_commit()
        flash(f"Rule '{name}' added successfully.", "success")
        return redirect(url_for('manage_rules'))

    rules = NotificationRule.query.all()

    # Get users with active subscriptions for the target user dropdown
    subbed_user_ids = db.session.query(PushSubscription.user_id).distinct().all()
    subbed_user_ids = [uid[0] for uid in subbed_user_ids]
    subscribed_users = User.query.filter(User.id.in_(subbed_user_ids)).order_by(User.username).all()

    return render_template('admin/rules_manager.html', rules=rules, subscribed_users=subscribed_users)

@app.route('/admin/rules/test_alert', methods=['POST'])
def test_alert():
    if not current_user.role == 'Admin' and current_user.role != 'Management':
        return jsonify({'status': 'error', 'message': 'Access Denied'}), 403

    test_type = request.form.get('test_type')
    target_user_id = request.form.get('target_user')

    if test_type == 'mortality':
        title = "SLH-OP: [TEST] Mortality"
        body = "VA2: Mortality exceeded 0.05% (TEST)"
    elif test_type == 'bodyweight':
        title = "SLH-OP: [TEST] Weight"
        body = "VA2: Week 47 weights updated (TEST)"
    else:
        return jsonify({'status': 'error', 'message': 'Invalid test type'}), 400

    query = PushSubscription.query
    if target_user_id and target_user_id != 'all':
        try:
            target_id = int(target_user_id)
            query = query.filter_by(user_id=target_id)
        except ValueError:
            pass

    subscriptions = query.all()
    successful_users = set()
    failed_count = 0

    unique_user_ids = list(set([sub.user_id for sub in subscriptions]))

    for uid in unique_user_ids:
        user = User.query.get(uid)
        if user:
            # send_push_alert returns boolean indicating if at least one sub succeeded
            success = send_push_alert(uid, title, body, transient=True)
            if success:
                successful_users.add(user.username)
            else:
                failed_count += 1

    return jsonify({
        'status': 'success',
        'successful_users': sorted(list(successful_users)),
        'failed_count': failed_count
    })

@app.route('/admin/rules/delete/<int:id>', methods=['POST'])
def delete_notification_rule(id):
    if not current_user.role == 'Admin' and current_user.role != 'Management':
        flash("Access Denied.", "danger")
        return redirect(url_for('index'))

    rule = NotificationRule.query.get_or_404(id)
    db.session.delete(rule)
    safe_commit()
    flash("Rule deleted.", "info")
    return redirect(url_for('manage_rules'))

@app.route('/admin/users')
@login_required
def admin_users():
    if not current_user.role == 'Admin':
        flash("Access Denied.", "danger")
        return redirect(url_for('index'))
    users = User.query.order_by(User.username).all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/users/add', methods=['POST'])
@login_required
def admin_user_add():
    if not current_user.role == 'Admin': return redirect(url_for('index'))

    username = request.form.get('username')
    name = request.form.get('name')
    password = request.form.get('password')
    dept = request.form.get('dept')
    role = request.form.get('role')
    farm_id = request.form.get('farm_id')

    if farm_id == '':
        farm_id = None

    if User.query.filter_by(username=username).first():
        flash(f"User {username} already exists.", "warning")
    else:
        u = User(username=username, name=name, dept=dept, role=role, farm_id=farm_id)
        u.set_password(password)
        db.session.add(u)
        safe_commit()
        flash(f"User {username} added.", "success")
    return redirect(url_for('admin_users'))

@app.route('/admin/users/edit/<int:user_id>', methods=['POST'])
@login_required
def admin_user_edit(user_id):
    if not current_user.role == 'Admin': return redirect(url_for('index'))

    user = User.query.get_or_404(user_id)
    name = request.form.get('name')
    dept = request.form.get('dept')
    role = request.form.get('role')

    user.name = name
    user.dept = dept
    user.role = role
    safe_commit()

    if user.id == current_user.id:
        session['user_name'] = user.name if user.name else user.username

    flash(f"User {user.username} updated.", "success")
    return redirect(url_for('admin_users'))

@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@login_required
def admin_user_delete(user_id):
    if not current_user.role == 'Admin': return redirect(url_for('index'))

    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Cannot delete yourself.", "danger")
    else:
        db.session.delete(user)
        safe_commit()
        flash(f"User {user.username} deleted.", "info")
    return redirect(url_for('admin_users'))

@app.route('/admin/users/reset_password/<int:user_id>', methods=['POST'])
@login_required
def admin_user_reset_password(user_id):
    if not current_user.role == 'Admin': return redirect(url_for('index'))

    user = User.query.get_or_404(user_id)
    new_pass = request.form.get('new_password')
    if new_pass:
        user.set_password(new_pass)
        safe_commit()
        flash(f"Password for {user.username} has been reset.", "success")
    else:
        flash("Password cannot be empty.", "danger")
    return redirect(url_for('admin_users'))

@app.route('/admin/project_report')
@login_required
def admin_project_report():
    if not current_user.role == 'Admin' and current_user.role != 'Management':
        flash("Access Denied: Admin or Management View Only.", "danger")
        return redirect(url_for('index'))
    return render_template('admin/project_report.html')

@app.route('/hatchery')
@login_required
@dept_required('Hatchery')
def hatchery_dashboard():
    active_flocks = Flock.query.options(joinedload(Flock.house)).filter_by(status='Active', phase='Production').all()

    if active_flocks:
            active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else ''))
    today = date.today()
    for f in active_flocks:
        days = (today - f.intake_date).days
        f.current_week = 0 if days == 0 else ((days - 1) // 7) + 1 if days > 0 else 0

    # Analytics: Current Month Hatchability (based on Hatch Date)
    start_month = date(today.year, today.month, 1)
    # Find records with hatching_date in current month
    # Note: hatching_date >= start_month
    # Ideally <= end_month, but >= start is fine for "current month so far"
    monthly_records = Hatchability.query.filter(Hatchability.hatching_date >= start_month).all()

    total_hatched = sum(r.hatched_chicks for r in monthly_records)
    total_set = sum(r.egg_set for r in monthly_records)

    avg_hatch_pct = (total_hatched / total_set * 100) if total_set > 0 else 0.0

    return render_template('hatchery_dashboard.html', active_flocks=active_flocks, avg_hatch_pct=avg_hatch_pct, current_month=today.strftime('%B %Y'))

@app.route('/')
@login_required
@dept_required('Farm')
def index():
    active_flocks = Flock.query.options(joinedload(Flock.logs).joinedload(DailyLog.partition_weights), joinedload(Flock.logs).joinedload(DailyLog.photos), joinedload(Flock.logs).joinedload(DailyLog.clinical_notes_list), joinedload(Flock.house)).filter_by(status='Active').all()

    # Inventory Check for Dashboard
    low_stock_items = InventoryItem.query.filter(InventoryItem.current_stock < InventoryItem.min_stock_level).all()
    low_stock_count = len(low_stock_items)
    normal_stock_items = InventoryItem.query.filter(InventoryItem.current_stock >= InventoryItem.min_stock_level).all()


    if active_flocks:
            active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else ''))

    today = date.today()
    yesterday = today - timedelta(days=1)

    for f in active_flocks:
        daily_stats = enrich_flock_data(f, f.logs)

        f.rearing_mort_m_pct = 0
        f.rearing_mort_f_pct = 0
        f.prod_mort_m_pct = 0
        f.prod_mort_f_pct = 0
        f.male_ratio_pct = 0
        f.has_log_today = False

        # Age
        days_age = (today - f.intake_date).days
        f.age_weeks = 0 if days_age == 0 else ((days_age - 1) // 7) + 1 if days_age > 0 else 0
        f.age_days = ((days_age - 1) % 7) + 1 if days_age > 0 else 0
        f.current_week = 0 if days_age == 0 else ((days_age - 1) // 7) + 1 if days_age > 0 else 0

        # Stats
        if daily_stats:
            last = daily_stats[-1]
            if last['date'] == today:
                f.has_log_today = True

            # Cumulative Pct (Phase specific)
            if getattr(f, 'calculated_phase', f.phase) in REARING_PHASES:
                f.rearing_mort_m_pct = last['mortality_cum_male_pct']
                f.rearing_mort_f_pct = last['mortality_cum_female_pct']
            else:
                f.prod_mort_m_pct = last['mortality_cum_male_pct']
                f.prod_mort_f_pct = last['mortality_cum_female_pct']

            if last['male_ratio_stock']:
                f.male_ratio_pct = last['male_ratio_stock']

        # Daily Stats & Trends
        f.daily_stats = {
            'mort_m_pct': 0, 'mort_f_pct': 0, 'egg_pct': 0,
            'mort_m_trend': 'flat', 'mort_f_trend': 'flat', 'egg_trend': 'flat',
            'mort_m_diff': 0, 'mort_f_diff': 0, 'egg_diff': 0,
            'has_today': False,
            'show_data': False,
            'data_date': None
        }

        # Map date -> stat
        stats_map = { d['date']: d for d in daily_stats }
        stats_today = stats_map.get(today)

        # Determine Display Data (Today or Latest)
        display_data = None
        if stats_today:
            f.daily_stats['has_today'] = True
            display_data = stats_today
        elif daily_stats:
            display_data = daily_stats[-1]

        if display_data:
            f.daily_stats['show_data'] = True
            f.daily_stats['data_date'] = display_data['date']

            f.daily_stats['mort_m_pct'] = display_data['mortality_male_pct']
            f.daily_stats['mort_f_pct'] = display_data['mortality_female_pct']
            f.daily_stats['egg_pct'] = display_data['egg_prod_pct']

            # Trend Calculation (vs Previous Day of DATA DATE)
            # Use previous AVAILABLE record if strict yesterday is missing?
            # Or use list index
            stats_prev = None
            if display_data in daily_stats:
                idx = daily_stats.index(display_data)
                if idx > 0:
                    stats_prev = daily_stats[idx-1]
            else:
                 # Fallback
                 prev_date = display_data['date'] - timedelta(days=1)
                 stats_prev = stats_map.get(prev_date)

            if stats_prev:
                f.daily_stats['mort_m_diff'] = display_data['mortality_male_pct'] - stats_prev['mortality_male_pct']
                f.daily_stats['mort_f_diff'] = display_data['mortality_female_pct'] - stats_prev['mortality_female_pct']
                f.daily_stats['egg_diff'] = display_data['egg_prod_pct'] - stats_prev['egg_prod_pct']

                if round(f.daily_stats['mort_m_diff'], 2) > 0: f.daily_stats['mort_m_trend'] = 'up'
                elif round(f.daily_stats['mort_m_diff'], 2) < 0: f.daily_stats['mort_m_trend'] = 'down'

                if round(f.daily_stats['mort_f_diff'], 2) > 0: f.daily_stats['mort_f_trend'] = 'up'
                elif round(f.daily_stats['mort_f_diff'], 2) < 0: f.daily_stats['mort_f_trend'] = 'down'

                if round(f.daily_stats['egg_diff'], 2) > 0: f.daily_stats['egg_trend'] = 'up'
                elif round(f.daily_stats['egg_diff'], 2) < 0: f.daily_stats['egg_trend'] = 'down'

    # Determine the date range for "This Week" (Monday to Sunday)
    weekday = today.weekday() # Monday is 0 and Sunday is 6
    this_week_start = today - timedelta(days=weekday)
    this_week_end = this_week_start + timedelta(days=6)

    # Determine the date range for "Next Week" (Monday to Sunday)
    next_week_start = this_week_end + timedelta(days=1)
    next_week_end = next_week_start + timedelta(days=6)

    active_flock_ids = [f.id for f in active_flocks]

    # Query uncompleted vaccines for these active flocks
    if active_flock_ids:
        uncompleted_vaccines = Vaccine.query.options(joinedload(Vaccine.flock).joinedload(Flock.house)).filter(
            Vaccine.flock_id.in_(active_flock_ids),
            Vaccine.est_date >= this_week_start,
            Vaccine.est_date <= next_week_end,
            Vaccine.actual_date.is_(None)
        ).order_by(Vaccine.est_date).all()
    else:
        uncompleted_vaccines = []

    this_week_vaccines = []
    next_week_vaccines = []

    for v in uncompleted_vaccines:
        if this_week_start <= v.est_date <= this_week_end:
            this_week_vaccines.append(v)
        elif next_week_start <= v.est_date <= next_week_end:
            next_week_vaccines.append(v)

    return render_template('index_modern.html',
                           active_flocks=active_flocks,
                           today=today,
                           low_stock_items=low_stock_items,
                           low_stock_count=low_stock_count,
                           normal_stock_items=normal_stock_items,
                           this_week_vaccines=this_week_vaccines,
                           next_week_vaccines=next_week_vaccines)

@app.route('/history')
@login_required
@dept_required('Farm')
def history():
    inactive_flocks = Flock.query.options(joinedload(Flock.house)).filter_by(status='Inactive').order_by(Flock.intake_date.desc()).all()
    return render_template('flock_history.html', inactive_flocks=inactive_flocks)

@app.route('/health_log/post_mortem', methods=['GET', 'POST'])
@login_required
@dept_required('Farm')
def health_log_post_mortem():
    if request.method == 'POST':
        flock_id = request.form.get('flock_id')
        date_str = request.form.get('date')
        clinical_notes = request.form.get('clinical_notes')

        if not flock_id or not date_str:
            flash("House and Date are required.", "danger")
            return redirect(url_for('health_log_post_mortem'))

        try:
            log_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            flash("Invalid date format.", "danger")
            return redirect(url_for('health_log_post_mortem'))

        # Find the existing log for this flock and date
        log = DailyLog.query.filter_by(flock_id=flock_id, date=log_date).first()

        # If it doesn't exist, create an empty one (as long as it complies with constraints)
        if not log:
            log = DailyLog(
                flock_id=flock_id,
                date=log_date,                body_weight_male=0,
                body_weight_female=0
            )
            db.session.add(log)
            db.session.flush() # get ID

        if clinical_notes and clinical_notes.strip() and clinical_notes.strip().lower() not in EMPTY_NOTE_VALUES:
            # If clinical_notes already exists, append or overwrite? User said update existing
            # Let's append with newline if existing
            if log.clinical_notes and log.clinical_notes.strip():
                log.clinical_notes += "\n" + clinical_notes.strip()
            else:
                log.clinical_notes = clinical_notes.strip()

        if 'photo' in request.files:
            files = request.files.getlist('photo')
            for file in files:
                if file and file.filename != '':
                    date_str_short = log.date.strftime('%y%m%d')
                    raw_name = f"{log.flock.flock_id}_{date_str_short}_{file.filename}"
                    filename = secure_filename(raw_name)
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)

                    new_photo = DailyLogPhoto(
                        log_id=log.id,
                        file_path=filepath,
                        original_filename=file.filename
                    )
                    db.session.add(new_photo)

        safe_commit()

        # Unconditional Push Alert
        try:
            house_name = log.flock.house.name if log.flock and log.flock.house else "Unknown House"
            title = "SLH-OP: Post Mortem"
            body = f"{house_name}: New Post Mortem report filed. Please review clinical findings."
            alert_url = url_for('view_flock', id=log.flock.id) if log.flock else '/'

            all_users = User.query.all()
            for user in all_users:
                send_push_alert(user.id, title, body, url=alert_url)
        except Exception as e:
            app.logger.error(f"Failed to send Post Mortem push alert: {str(e)}")

        flash("Post Mortem details saved successfully.", "success")
        return redirect(url_for('health_log_post_mortem'))

    # Handle GET request (History view)
    house_id = request.args.get('house_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    search = request.args.get('search', '').strip()

    # Base Query: Has notes OR photo
    query = DailyLog.query.join(Flock).join(House).outerjoin(DailyLogPhoto).filter(
        or_(
            and_(DailyLog.clinical_notes != None, DailyLog.clinical_notes != ''),
            DailyLogPhoto.id != None
        )
    ).distinct()

    if house_id:
        query = query.filter(Flock.house_id == house_id)

    if start_date:
        try:
            s_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            query = query.filter(DailyLog.date >= s_date)
        except ValueError: pass

    if end_date:
        try:
            e_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            query = query.filter(DailyLog.date <= e_date)
        except ValueError: pass

    if search:
        term = f"%{search}%"
        query = query.filter(DailyLog.clinical_notes.ilike(term))

    logs = query.order_by(DailyLog.date.desc()).all()

    active_flocks = Flock.query.options(joinedload(Flock.house)).filter_by(status='Active').all()

    if active_flocks:
            active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else ''))

    houses = House.query.order_by(House.name).all()
    return render_template('post_mortem.html', logs=logs, houses=houses, active_flocks=active_flocks, today=date.today())

@app.route('/flock/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@dept_required('Farm')
def edit_flock(id):
    flock = Flock.query.get_or_404(id)
    if request.method == 'POST':
        old_data = {
            'flock_id': flock.flock_id,
            'intake_date': flock.intake_date.strftime('%Y-%m-%d') if flock.intake_date else None,
            'intake_male': flock.intake_male,
            'intake_female': flock.intake_female
        }

        # Flock ID (ID) Update
        new_flock_id = request.form.get('flock_id').strip()
        if new_flock_id and new_flock_id != flock.flock_id:
            # Check for uniqueness
            existing = Flock.query.filter_by(flock_id=new_flock_id).first()
            if existing:
                flash(f'Error: Flock ID "{new_flock_id}" already exists.', 'danger')
                return render_template('flock_edit.html', flock=flock)
            flock.flock_id = new_flock_id

        intake_date_str = request.form.get('intake_date')
        if intake_date_str:
            flock.intake_date = datetime.strptime(intake_date_str, '%Y-%m-%d').date()

        # production_start_date is now dynamic based on egg_prod_pct >= 5.0, so no direct assignment

        lay_date_str = request.form.get('start_of_lay_date')
        if lay_date_str:
             flock.start_of_lay_date = datetime.strptime(lay_date_str, '%Y-%m-%d').date()
        else:
             flock.start_of_lay_date = None

        flock.intake_male = int(request.form.get('intake_male') or 0)
        flock.intake_female = int(request.form.get('intake_female') or 0)
        flock.doa_male = int(request.form.get('doa_male') or 0)
        flock.doa_female = int(request.form.get('doa_female') or 0)

        flock.prod_start_male = int(request.form.get('prod_start_male') or 0)
        flock.prod_start_female = int(request.form.get('prod_start_female') or 0)
        flock.prod_start_male_hosp = int(request.form.get('prod_start_male_hosp') or 0)
        flock.prod_start_female_hosp = int(request.form.get('prod_start_female_hosp') or 0)

        # Farm Update
        farm_name = request.form.get('farm_name', '').strip()
        if not farm_name:
            flash('Error: Farm name is required.', 'danger')
            return render_template('flock_edit.html', flock=flock)

        farm = Farm.query.filter_by(name=farm_name).first()
        if not farm:
            farm = Farm(name=farm_name)
            db.session.add(farm)
            safe_commit()
        flock.farm_id = farm.id

        new_data = {
            'flock_id': flock.flock_id,
            'intake_date': flock.intake_date.strftime('%Y-%m-%d') if flock.intake_date else None,
            'intake_male': flock.intake_male,
            'intake_female': flock.intake_female
        }

        changes = {k: {'old': old_data[k], 'new': new_data[k]} for k in old_data if old_data[k] != new_data[k]}
        if changes:
            log_user_activity(current_user.id, 'Edit', 'Flock', flock.flock_id, details=changes)

        safe_commit()
        flash(f'Flock {flock.flock_id} updated.', 'success')
        return redirect(url_for('index'))

    farms = Farm.query.all()
    return render_template('flock_edit.html', flock=flock, farms=farms)

@app.route('/flock/<int:id>/delete', methods=['POST'])
@login_required
@dept_required('Farm')
def delete_flock(id):
    flock = Flock.query.get_or_404(id)
    flock_id_str = flock.flock_id

    log_user_activity(current_user.id, 'Delete', 'Flock', flock_id_str)

    db.session.delete(flock)
    safe_commit()
    flash(f'Flock {flock_id_str} deleted.', 'warning')
    return redirect(url_for('manage_flocks'))

@app.route('/flock_select')
@login_required
@dept_required('Farm')
def flock_select():
    active_flocks = Flock.query.options(joinedload(Flock.house)).filter_by(status='Active').all()

    if active_flocks:
            active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else ''))

    if not active_flocks:
        flash("No active flocks found.", "warning")
        return redirect(url_for('index'))

    return render_template('flock_select.html', active_flocks=active_flocks)

@app.route('/flocks', methods=['GET', 'POST'])
@login_required
@dept_required('Farm')
def manage_flocks():
    if request.method == 'POST':
        house_name = request.form.get('house_name').strip()
        intake_date_str = request.form.get('intake_date')

        # production_start_date is now dynamic based on egg_prod_pct >= 5.0, so no direct assignment

        intake_male = int(request.form.get('intake_male') or 0)
        intake_female = int(request.form.get('intake_female') or 0)
        doa_male = int(request.form.get('doa_male') or 0)
        doa_female = int(request.form.get('doa_female') or 0)
        
        # Find or Create Farm
        farm_name = request.form.get('farm_name', '').strip()
        if not farm_name:
            flash('Error: Farm name is required.', 'danger')
            return redirect(url_for('manage_flocks'))

        farm_id = None
        farm = Farm.query.filter_by(name=farm_name).first()
        if not farm:
            farm = Farm(name=farm_name)
            db.session.add(farm)
            safe_commit()
            flash(f'Created new Farm: {farm_name}', 'info')
        farm_id = farm.id

        # Find or Create House
        house = House.query.filter_by(name=house_name).first()
        if not house:
            house = House(name=house_name)
            db.session.add(house)
            safe_commit()
            flash(f'Created new House: {house_name}', 'info')
        
        # Validation: Check if House has active flock
        existing_active = Flock.query.filter_by(house_id=house.id, status='Active').first()
        if existing_active:
            flash(f'Error: House {house.name} already has an active flock (Batch: {existing_active.flock_id})', 'danger')
            return redirect(url_for('manage_flocks'))
        
        # Generate Flock ID
        intake_date = datetime.strptime(intake_date_str, '%Y-%m-%d').date()
        date_str = intake_date.strftime('%y%m%d')
        
        # Calculate N (Total flocks for this house + 1)
        house_flock_count = Flock.query.filter_by(house_id=house.id).count()
        n = house_flock_count + 1
        
        flock_id = f"{house.name}_{date_str}_Batch{n}"
        
        new_flock = Flock(
            house_id=house.id,
            farm_id=farm_id,
            flock_id=flock_id,
            intake_date=intake_date,
            intake_male=intake_male,
            intake_female=intake_female,
            doa_male=doa_male,
            doa_female=doa_female
        )
        
        db.session.add(new_flock)
        db.session.flush()

        log_user_activity(current_user.id, 'Add', 'Flock', new_flock.flock_id, details={
            'house': house_name,
            'intake_male': intake_male,
            'intake_female': intake_female
        })

        safe_commit()

        initialize_sampling_schedule(new_flock.id)
        initialize_vaccine_schedule(new_flock.id)

        flash(f'Flock created successfully! Flock ID: {flock_id}', 'success')
        return redirect(url_for('index'))
    
    farms = Farm.query.all()
    houses = House.query.all()
    flocks = Flock.query.options(joinedload(Flock.house)).order_by(Flock.intake_date.desc()).all()

    # Bulk fetch cumulative mortality for all flocks to prevent N+1 queries
    # Using coalesce to handle NULL values correctly in SQL addition
    mortality_data = db.session.query(
        DailyLog.flock_id,
        db.func.sum(
            db.func.coalesce(DailyLog.mortality_male, 0) +
            db.func.coalesce(DailyLog.mortality_female, 0) +
            db.func.coalesce(DailyLog.culls_male, 0) +
            db.func.coalesce(DailyLog.culls_female, 0) +
            db.func.coalesce(DailyLog.mortality_male_hosp, 0) +
            db.func.coalesce(DailyLog.mortality_female_hosp, 0) +
            db.func.coalesce(DailyLog.culls_male_hosp, 0) +
            db.func.coalesce(DailyLog.culls_female_hosp, 0)
        )
    ).group_by(DailyLog.flock_id).all()

    mortality_map = {row[0]: row[1] for row in mortality_data}

    for flock in flocks:
        intake_m = flock.intake_male or 0
        intake_f = flock.intake_female or 0
        total_intake = intake_m + intake_f

        if total_intake > 0:
            cum_mort = mortality_map.get(flock.id, 0)
            flock.lifetime_cum_mort_pct = round((cum_mort / total_intake) * 100, 2)
        else:
            flock.lifetime_cum_mort_pct = 0.0

    return render_template('flock_form.html', farms=farms, houses=houses, flocks=flocks)

@app.route('/flock/<int:id>/close', methods=['POST'])
@login_required
@dept_required('Farm')
def close_flock(id):
    flock = Flock.query.get_or_404(id)
    flock.status = 'Inactive'
    flock.end_date = date.today()
    safe_commit()
    flash(f'Flock {flock.flock_id} closed.', 'info')
    return redirect(url_for('index'))

@app.route('/standards', methods=['GET', 'POST'])
@login_required
@dept_required('Farm')
def manage_standards():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            week_val = request.form.get('week')
            if not week_val or not week_val.isdigit():
                flash('Invalid or missing week number.', 'danger')
                return redirect(url_for('manage_standards'))

            pw_val = request.form.get('production_week')
            prod_week = int(pw_val) if pw_val and pw_val.isdigit() else None

            s = Standard(
                week=int(week_val),
                production_week=prod_week,
                std_mortality_male=float(request.form.get('std_mortality_male') or 0),
                std_mortality_female=float(request.form.get('std_mortality_female') or 0),
                std_bw_male=round_to_whole(request.form.get('std_bw_male')),
                std_bw_female=round_to_whole(request.form.get('std_bw_female')),
                std_egg_prod=float(request.form.get('std_egg_prod') or 0),
                std_egg_weight=float(request.form.get('std_egg_weight') or 0),
                std_hatchability=float(request.form.get('std_hatchability') or 0),
                std_cum_eggs_hha=float(request.form.get('std_cum_eggs_hha') or 0),
                std_cum_hatching_eggs_hha=float(request.form.get('std_cum_hatching_eggs_hha') or 0),
                std_cum_chicks_hha=float(request.form.get('std_cum_chicks_hha') or 0)
            )
            db.session.add(s)
            safe_commit()
            flash('Standard added.', 'success')
        elif action == 'update':
            s_id = request.form.get('id')
            s = Standard.query.get(s_id)
            if s:
                pw_val = request.form.get('production_week')
                s.production_week = int(pw_val) if pw_val and pw_val.isdigit() else None

                s.std_mortality_male=float(request.form.get('std_mortality_male') or 0)
                s.std_mortality_female=float(request.form.get('std_mortality_female') or 0)
                s.std_bw_male=round_to_whole(request.form.get('std_bw_male'))
                s.std_bw_female=round_to_whole(request.form.get('std_bw_female'))
                s.std_egg_prod=float(request.form.get('std_egg_prod') or 0)
                s.std_egg_weight=float(request.form.get('std_egg_weight') or 0)
                s.std_hatchability=float(request.form.get('std_hatchability') or 0)
                s.std_cum_eggs_hha=float(request.form.get('std_cum_eggs_hha') or 0)
                s.std_cum_hatching_eggs_hha=float(request.form.get('std_cum_hatching_eggs_hha') or 0)
                s.std_cum_chicks_hha=float(request.form.get('std_cum_chicks_hha') or 0)

                safe_commit()
                flash(f'Standard for Week {s.week} updated.', 'success')
            else:
                flash('Standard not found.', 'danger')

        elif action == 'update_global':
            gs = GlobalStandard.query.first()
            if not gs:
                gs = GlobalStandard()
                db.session.add(gs)

            gs.std_mortality_daily = float(request.form.get('std_mortality_daily') or 0.05)
            gs.std_mortality_weekly = float(request.form.get('std_mortality_weekly') or 0.3)
            gs.std_hatching_egg_pct = float(request.form.get('std_hatching_egg_pct') or 96.0)
            safe_commit()
            flash('Global standards updated.', 'success')

        elif action == 'seed_standards':
            success, message = seed_standards_from_file()
            if success:
                flash(message, 'success')
            else:
                flash(message, 'danger')
        elif action == 'seed_arbor_acres':
            success, message = seed_arbor_acres_standards()
            if success:
                flash(message, 'success')
            else:
                flash(message, 'danger')

        return redirect(url_for('manage_standards'))

    standards = Standard.query.order_by(Standard.week.asc()).all()
    global_std = GlobalStandard.query.first()
    if not global_std:
        global_std = GlobalStandard() # Default values from model

    return render_template('standards.html', standards=standards, global_std=global_std)

@app.route('/feed_codes', methods=['GET', 'POST'])
@login_required
@dept_required('Farm')
def manage_feed_codes():
    if request.method == 'POST':
        code = request.form.get('code').strip()
        if code:
            existing = FeedCode.query.filter_by(code=code).first()
            if existing:
                flash(f'Feed Code {code} already exists.', 'warning')
            else:
                db.session.add(FeedCode(code=code))
                safe_commit()
                flash(f'Feed Code {code} added.', 'success')
        return redirect(url_for('manage_feed_codes'))

    if FeedCode.query.count() == 0:
        default_codes = ['161C', '162C', '163C', '168C', '169C', '170P', '171P', '172P']
        for c in default_codes:
            db.session.add(FeedCode(code=c))
        safe_commit()

    codes = FeedCode.query.order_by(FeedCode.code.asc()).all()
    return render_template('feed_codes.html', codes=codes)

@app.route('/feed_codes/delete/<int:id>', methods=['POST'])
@login_required
@dept_required('Farm')
def delete_feed_code(id):
    fc = FeedCode.query.get_or_404(id)
    db.session.delete(fc)
    safe_commit()
    flash(f'Feed Code {fc.code} deleted.', 'info')
    return redirect(url_for('manage_feed_codes'))

@app.route('/daily_log/delete/<int:id>', methods=['POST'])
@login_required
@dept_required('Farm')
def delete_daily_log(id):
    if not current_user.role == 'Admin': return redirect(url_for('index'))

    log = DailyLog.query.get_or_404(id)
    flock_id = log.flock_id
    date_str = log.date.strftime('%Y-%m-%d')

    log_user_activity(current_user.id, 'Delete', 'DailyLog', log.id, details={'date': date_str, 'flock_id': flock_id})

    # Cascade delete handles partitions, but maybe not Inventory Transactions (Usage)?
    # We should probably revert usage if tracked?
    # But usage is tracked via Medication start date or "Used in Daily Log" notes.
    # The 'daily_log' submission creates 'Medication' records.
    # We can try to find medications created on this date for this flock?
    # But medication might span multiple days.
    # Deleting a log is complex regarding side effects.
    # For now, just delete the log record itself (metrics).
    # Reverting inventory is too risky without explicit link.

    db.session.delete(log)
    safe_commit()
    flash("Daily Log deleted.", "info")
    return redirect(url_for('view_flock', id=flock_id))

@app.route('/daily_log/photo/<int:photo_id>/delete', methods=['DELETE'])
@login_required
@dept_required('Farm')
def delete_daily_log_photo(photo_id):
    photo = DailyLogPhoto.query.get_or_404(photo_id)
    # Check ownership/permissions if strict, but @dept_required('Farm') is enough for now.

    # Delete file from disk
    if photo.file_path and os.path.exists(photo.file_path):
        try:
            os.remove(photo.file_path)
        except OSError:
            pass # Ignore if file missing

    db.session.delete(photo)
    safe_commit()
    return '', 204

@app.route('/api/chart_data/<int:flock_id>')
@login_required
@dept_required('Farm')
def get_chart_data(flock_id):
    flock = Flock.query.get_or_404(flock_id)

    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    mode = request.args.get('mode', 'daily') # 'daily', 'weekly', 'monthly'

    hatch_records = Hatchability.query.filter_by(flock_id=flock_id).all()
    all_logs = DailyLog.query.options(joinedload(DailyLog.photos), joinedload(DailyLog.clinical_notes_list)).filter_by(flock_id=flock_id).order_by(DailyLog.date.asc()).all()

    # Fetch Health Data
    meds = Medication.query.filter_by(flock_id=flock_id).all()
    vacs = Vaccine.query.filter_by(flock_id=flock_id).filter(Vaccine.actual_date != None).all()

    daily_stats = enrich_flock_data(flock, all_logs, hatch_records)

    filtered_daily = []
    for d in daily_stats:
        if start_date_str and d['date'] < datetime.strptime(start_date_str, '%Y-%m-%d').date(): continue
        if end_date_str and d['date'] > datetime.strptime(end_date_str, '%Y-%m-%d').date(): continue
        filtered_daily.append(d)

    data = {
        'flock_id': flock.flock_id,
        'intake_date': flock.intake_date.isoformat(),
        'dates': [],
        'weeks': [],
        'ranges': [],
        'metrics': {
            'mortality_f_pct': [], 'mortality_m_pct': [],
            'culls_f_pct': [], 'culls_m_pct': [],
            'egg_prod_pct': [], 'hatch_egg_pct': [],
            'bw_f': [], 'bw_m': [],
            'uni_f': [], 'uni_m': [],
            'feed_f': [], 'feed_m': [],
            'water_per_bird': [],
            'water_feed_ratio': [],
        },
        'events': []
    }

    if mode == 'daily':
        data['dates'] = [d['date'].isoformat() for d in filtered_daily]
        for d in filtered_daily:
            # We map Mortality % + Culls % to 'mortality_X_pct' in the chart logic usually?
            # Existing code: daily_mort_f_pct = (((log.mortality_female or 0) + (log.culls_female or 0)) / curr_stock_f) * 100
            # metrics.py separates them.
            # But the chart keys are: 'mortality_f_pct'.
            # I should combine them to match legacy chart behavior: "Depletion %"

            mort_f = d['mortality_female_pct'] + d['culls_female_pct']
            mort_m = d['mortality_male_pct'] + d['culls_male_pct']

            data['metrics']['mortality_f_pct'].append(round(mort_f, 2))
            data['metrics']['mortality_m_pct'].append(round(mort_m, 2))
            data['metrics']['egg_prod_pct'].append(round(d['egg_prod_pct'], 2))
            data['metrics']['hatch_egg_pct'].append(round(d['hatch_egg_pct'], 2))
            data['metrics']['bw_f'].append(d['body_weight_female'])
            data['metrics']['bw_m'].append(d['body_weight_male'])
            data['metrics']['uni_f'].append(d['uniformity_female'])
            data['metrics']['uni_m'].append(d['uniformity_male'])
            data['metrics']['feed_f'].append(d['feed_female_gp_bird'])
            data['metrics']['feed_m'].append(d['feed_male_gp_bird'])
            data['metrics']['water_per_bird'].append(round(d['water_per_bird'], 1) if d['water_per_bird'] >= 0 else None)
            data['metrics']['water_feed_ratio'].append(round(d.get('water_feed_ratio'), 2) if d.get('water_feed_ratio') is not None and d.get('water_feed_ratio') >= 0 else None)

            log = d['log']

            # Temporarily disabled to prevent OSError: write error on massive payload sizes
            # # Construct Note content
            # note_parts = []
            # if log.flushing: note_parts.append("[FLUSHING]")
            # if log.clinical_notes: note_parts.append(log.clinical_notes)
            #
            # # Active Meds
            # active_meds = [m.drug_name for m in meds if m.start_date <= log.date and (m.end_date is None or m.end_date >= log.date)]
            # if active_meds:
            #     note_parts.append("Meds: " + ", ".join(active_meds))
            #
            # # Completed Vaccines
            # done_vacs = [v.vaccine_name for v in vacs if v.actual_date == log.date]
            # if done_vacs:
            #     note_parts.append("Vac: " + ", ".join(done_vacs))
            #
            # # Main Photos
            # main_photos = [p for p in log.photos if p.note_id is None]
            #
            # # Extra Notes
            # extra_notes = []
            # if log.clinical_notes_list:
            #     for n in log.clinical_notes_list:
            #         n_photos = []
            #         for p in n.photos:
            #             n_photos.append({
            #                 'url': url_for('uploaded_file', filename=os.path.basename(p.file_path)),
            #                 'name': p.original_filename or 'Photo'
            #             })
            #         extra_notes.append({
            #             'caption': n.caption,
            #             'photos': n_photos
            #         })
            #
            # has_data = (note_parts or main_photos or extra_notes)
            #
            # if has_data:
            #     main_photo_list = []
            #     for p in main_photos:
            #         main_photo_list.append({
            #             'url': url_for('uploaded_file', filename=os.path.basename(p.file_path)),
            #             'name': p.original_filename or 'Photo'
            #         })
            #
            #     data['events'].append({
            #         'date': log.date.isoformat(),
            #         'note': " | ".join(note_parts),
            #         'main_note': " | ".join(note_parts),
            #         'photos': main_photo_list,
            #         'main_photos': main_photo_list,
            #         'extra_notes': extra_notes,
            #         'type': 'note'
            #     })

    else:
        # Aggregated
        if mode == 'weekly':
            agg_stats = aggregate_weekly_metrics(filtered_daily)
            label_prefix = "Week "
            data['weeks'] = [a['week'] for a in agg_stats]
        else:
            agg_stats = aggregate_monthly_metrics(filtered_daily)
            label_prefix = ""

        for a in agg_stats:
            lbl = f"{label_prefix}{a['week']}" if mode == 'weekly' else a['month']
            data['dates'].append(lbl)
            data['ranges'].append({'start': a['date_start'].isoformat(), 'end': a['date_end'].isoformat()})

            # Combine Mort + Cull for Depletion
            mort_f = a['mortality_female_pct'] + a['culls_female_pct']
            mort_m = a['mortality_male_pct'] + a['culls_male_pct']

            data['metrics']['mortality_f_pct'].append(round(mort_f, 2))
            data['metrics']['mortality_m_pct'].append(round(mort_m, 2))
            data['metrics']['egg_prod_pct'].append(round(a['egg_prod_pct'], 2))
            data['metrics']['hatch_egg_pct'].append(round(a['hatch_egg_pct'], 2))
            data['metrics']['bw_f'].append(round(a['body_weight_female'], 0))
            data['metrics']['bw_m'].append(round(a['body_weight_male'], 0))
            data['metrics']['uni_f'].append(round(a['uniformity_female'], 2))
            data['metrics']['uni_m'].append(round(a['uniformity_male'], 2))
            # Feed in agg is total kg? Or average g/bird?
            # aggregate_weekly_metrics does NOT return avg g/bird. It returns total_kg.
            # But the chart expects g/bird.
            # I need to calculate avg g/bird from total_kg and stock.
            # Avg g/bird = (Total Kg * 1000) / (Avg Stock * Days)

            days_count = (a['date_end'] - a['date_start']).days + 1
            avg_stock_m = a['stock_male_start'] # Approx
            avg_stock_f = a['stock_female_start']

            # This is hard because metrics.py didn't separate feed male/female kg in aggregation.
            # It only has 'feed_total_kg'.
            # I need to update metrics.py to aggregate feed_m_kg and feed_f_kg separately if I want this chart.
            # For now, I'll return 0 or calculate if possible.
            # Wait, daily_stats has 'feed_male_gp_bird'.
            # I should iterate daily stats inside aggregation to get average feed/bird?
            # Or just update metrics.py.

            data['metrics']['feed_f'].append(round(a['feed_female_gp_bird'], 2))
            data['metrics']['feed_m'].append(round(a['feed_male_gp_bird'], 2))
            data['metrics']['water_per_bird'].append(round(a['water_per_bird'], 1) if a.get('water_per_bird', 0) >= 0 else None)
            data['metrics']['water_feed_ratio'].append(round(a.get('water_feed_ratio'), 2) if a.get('water_feed_ratio') is not None and a.get('water_feed_ratio') >= 0 else None)

    return data

def calculate_flock_summary(flock, daily_stats):
    """
    Calculates the 'Summary' tab data:
    1. Dashboard: Current Totals vs Depletion Targets.
    2. Weekly Table: Cumulative metrics from Start of Production.
    """

    # 1. Determine Start of Production & Females Housed
    start_date = flock.production_start_date
    start_stock = flock.prod_start_female

    if not start_date:
        # Fallback: Try to find start date from logs (Production Week 1)
        first_prod_log = next((d for d in daily_stats if d.get('production_week') and d['production_week'] >= 1), None)
        if first_prod_log:
            start_date = first_prod_log['date']
            if start_stock == 0:
                start_stock = first_prod_log['stock_female_start']
        else:
            return None, []

    # If start_date is found but start_stock is 0 (User entered 0 or missing)
    if start_stock == 0 and start_date:
        # Find stock on that date from daily_stats
        log_on_start = next((d for d in daily_stats if d['date'] == start_date), None)
        if log_on_start:
            start_stock = log_on_start['stock_female_start']
        else:
            # If no log exactly on start date, find first log after start date
            first_log_after = next((d for d in daily_stats if d['date'] > start_date), None)
            if first_log_after:
                start_stock = first_log_after['stock_female_start']

    if start_stock <= 0:
        start_stock = 1 # Avoid div by zero

    # 2. Iterate daily_stats
    # Filter for production period
    prod_stats = [d for d in daily_stats if d['date'] >= start_date]

    # Group by Production Week

    # Standards Map
    all_standards = Standard.query.all()
    std_map = {getattr(s, 'production_week'): s for s in all_standards if hasattr(s, 'production_week') and getattr(s, 'production_week')}

    cum_eggs = 0
    cum_hatch_eggs = 0
    cum_feed = 0
    cum_chicks = 0

    summary_table = []
    dashboard_metrics = {}

    # Grouping
    by_week = {}
    for d in prod_stats:
        pw = d.get('production_week')
        if not pw: continue
        if pw not in by_week: by_week[pw] = []
        by_week[pw].append(d)

    sorted_weeks = sorted(by_week.keys())

    for pw in sorted_weeks:
        days = by_week[pw]

        # Weekly Sums
        w_eggs = sum(d['eggs_collected'] for d in days)
        w_hatch_eggs = sum(d['hatch_eggs'] for d in days)
        w_feed = sum(d['feed_f_kg'] for d in days) # Use calculated Kg from enrichment
        w_chicks = sum(d['hatched_chicks'] or 0 for d in days)

        # Update Cumulative
        cum_eggs += w_eggs
        cum_hatch_eggs += w_hatch_eggs
        cum_feed += w_feed
        cum_chicks += w_chicks

        # Metrics
        hha_total = cum_eggs / start_stock
        hha_hatch = cum_hatch_eggs / start_stock
        hha_chicks = cum_chicks / start_stock

        feed_100_chicks = (cum_feed / cum_chicks * 100) if cum_chicks > 0 else 0
        feed_100_h_eggs = (cum_feed / cum_hatch_eggs * 100) if cum_hatch_eggs > 0 else 0

        # Liveability
        last_day = days[-1]
        current_live = last_day.get('stock_female_prod_end', 0)

        liveability = (current_live / start_stock * 100)

        # Standard
        std = std_map.get(pw)
        std_hha_total = (std.std_cum_eggs_hha if std and std.std_cum_eggs_hha is not None else 0.0)
        std_hha_chicks = (std.std_cum_chicks_hha if std and std.std_cum_chicks_hha is not None else 0.0)

        # Estimate Hatching Eggs HHA Target (From Standard if available, else Global %)
        if std and std.std_cum_hatching_eggs_hha:
            std_hha_hatch = std.std_cum_hatching_eggs_hha
        else:
            # Using Global Standard if available, else 96%
            gs = GlobalStandard.query.first()
            std_he_pct = gs.std_hatching_egg_pct if gs else 96.0
            std_hha_hatch = std_hha_total * (std_he_pct / 100.0)

        row = {
            'week': pw,
            'age': days[-1]['week'], # Bio Week
            'cum_eggs_hha': round(hha_total, 1),
            'std_cum_eggs_hha': std_hha_total,
            'cum_hatch_hha': round(hha_hatch, 1),
            'std_cum_hatching_eggs_hha': round(std_hha_hatch, 1),
            'cum_chicks_hha': round(hha_chicks, 1),
            'std_cum_chicks_hha': std_hha_chicks,
            'feed_100_chicks': round(feed_100_chicks, 1),
            'feed_100_h_eggs': round(feed_100_h_eggs, 1),
            'liveability': round(liveability, 2)
        }
        summary_table.append(row)

        # Feed Targets (Placeholder or Derived if Standard table doesn't have them)
        # For now, we set them to 0 if not available to avoid hardcoded mismatch
        std_feed_chicks = 0
        std_feed_h_eggs = 0

        # Update Dashboard (Last valid week overwrites previous)
        dashboard_metrics = {
            'week': pw,
            'age': days[-1]['week'],
            'hha_total': round(hha_total, 1),
            'hha_total_std': round(std_hha_total, 1),
            'hha_hatch': round(hha_hatch, 1),
            'hha_hatch_std': round(std_hha_hatch, 1),
            'hha_chicks': round(hha_chicks, 1),
            'hha_chicks_std': round(std_hha_chicks, 1),
            'liveability': round(liveability, 2),
            'feed_100_chicks': round(feed_100_chicks, 1),
            'feed_100_chicks_std': std_feed_chicks, # Dynamic or 0
            'feed_100_h_eggs': round(feed_100_h_eggs, 1),
            'feed_100_h_eggs_std': std_feed_h_eggs # Dynamic or 0
        }

    return dashboard_metrics, summary_table

@app.route('/flock/<int:id>/toggle_phase', methods=['POST'])
@login_required
@dept_required('Farm')
def toggle_phase(id):
    flock = Flock.query.get_or_404(id)
    if flock.phase == 'Rearing':
        flock.phase = 'Production'

        # production_start_date is now dynamic based on egg_prod_pct >= 5.0, so no direct assignment

        # Capture Start Counts
        prod_m = int(request.form.get('prod_start_male') or 0)
        prod_f = int(request.form.get('prod_start_female') or 0)
        hosp_m = int(request.form.get('prod_start_male_hosp') or 0)
        hosp_f = int(request.form.get('prod_start_female_hosp') or 0)

        flock.prod_start_male = prod_m
        flock.prod_start_female = prod_f
        flock.prod_start_male_hosp = hosp_m
        flock.prod_start_female_hosp = hosp_f

        # Calculate Loss Check (Expected vs Actual)
        stmt = db.session.query(
            db.func.sum(DailyLog.mortality_male),
            db.func.sum(DailyLog.mortality_female),
            db.func.sum(DailyLog.culls_male),
            db.func.sum(DailyLog.culls_female)
        ).filter(DailyLog.flock_id == id).first()

        rearing_loss_m = (stmt[0] or 0) + (stmt[2] or 0)
        rearing_loss_f = (stmt[1] or 0) + (stmt[3] or 0)

        expected_m = flock.intake_male - rearing_loss_m
        expected_f = flock.intake_female - rearing_loss_f

        actual_m = prod_m + hosp_m
        actual_f = prod_f + hosp_f

        diff_m = expected_m - actual_m
        diff_f = expected_f - actual_f

        msg = (
            f"Flock {flock.flock_id} switched to Production."
            f"{f' Warning: Count Discrepancy (M: {diff_m}, F: {diff_f}). Baseline reset to {actual_m} M / {actual_f} F.' if (diff_m != 0 or diff_f != 0) else ''}"
        )
        flash(msg, 'success' if (diff_m == 0 and diff_f == 0) else 'warning')
    else:
        flock.phase = 'Rearing'
        flash(f'Flock {flock.flock_id} switched back to Rearing phase.', 'warning')
    safe_commit()
    return redirect(url_for('index'))

@app.route('/flock/<int:id>')
@login_required
@dept_required('Farm')
def view_flock(id):
    active_flocks = Flock.query.options(joinedload(Flock.house)).filter_by(status='Active').all()

    if active_flocks:
            active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else ''))

    flock = Flock.query.options(joinedload(Flock.house)).filter_by(id=id).first_or_404()
    logs = DailyLog.query.options(joinedload(DailyLog.partition_weights), joinedload(DailyLog.photos), joinedload(DailyLog.clinical_notes_list)).filter_by(flock_id=id).order_by(DailyLog.date.asc()).all()

    # --- Health Analytics ---
    health_events = analyze_health_events(logs)

    gs = GlobalStandard.query.first()
    if not gs:
        gs = GlobalStandard()
        db.session.add(gs)
        safe_commit()

    # --- Standards Setup ---
    all_standards = Standard.query.all()
    std_map = {getattr(s, 'week'): s for s in all_standards if hasattr(s, 'week')} # Biological Age Map
    prod_std_map = {getattr(s, 'production_week'): s for s in all_standards if hasattr(s, 'production_week') and getattr(s, 'production_week')} # Production Week Map

    # --- Fetch Hatch Data ---
    hatch_records = Hatchability.query.filter_by(flock_id=id).order_by(Hatchability.setting_date.desc()).all()

    # --- Metrics Engine ---
    daily_stats = enrich_flock_data(flock, logs, hatch_records)

    # --- Calculate Summary Tab Data ---
    summary_dashboard, summary_table = calculate_flock_summary(flock, daily_stats)

    # Inject Standards
    for d in daily_stats:
        # Production Metrics (Egg Prod, Weight, Hatch) -> Use Production Week
        prod_std = None
        if d.get('production_week'):
            prod_std = prod_std_map.get(d['production_week'])

        d['std_egg_prod'] = (prod_std.std_egg_prod if prod_std and prod_std.std_egg_prod is not None else 0.0)
        d['std_hatching_egg_pct'] = (prod_std.std_hatching_egg_pct if prod_std and prod_std.std_hatching_egg_pct is not None else 0.0)
        # Add other production standards if needed by template

    weekly_stats = aggregate_weekly_metrics(daily_stats)

    for ws in weekly_stats:
        prod_std = None
        if ws.get('production_week'):
            prod_std = prod_std_map.get(ws['production_week'])

        ws['std_egg_prod'] = (prod_std.std_egg_prod if prod_std and prod_std.std_egg_prod is not None else 0.0)
        ws['std_hatching_egg_pct'] = (prod_std.std_hatching_egg_pct if prod_std and prod_std.std_hatching_egg_pct is not None else 0.0)

    medications = Medication.query.filter_by(flock_id=id).all()
    vacs = Vaccine.query.filter_by(flock_id=id).filter(Vaccine.actual_date != None).all()

    # 1. Enriched Logs (For Table)
    enriched_logs = []

    def scale_pct(val):
        if val is None: return None
        if 0 < val <= 1.0: return val * 100.0
        return val

    for d in daily_stats:
        log = d['log']
        
        # View Specific: Lighting
        lighting_hours = 0
        if log.light_on_time and log.light_off_time:
            try:
                fmt = '%H:%M'
                t1 = datetime.strptime(log.light_on_time, fmt)
                t2 = datetime.strptime(log.light_off_time, fmt)
                diff = (t2 - t1).total_seconds() / 3600
                if diff < 0: diff += 24
                lighting_hours = round(diff, 1)
            except: pass

        # View Specific: Meds
        active_meds = []
        for m in medications:
            if m.start_date <= log.date:
                if m.end_date is None or m.end_date >= log.date:
                    active_meds.append(m.drug_name)
        meds_str = ", ".join(active_meds)

        cleanup_duration_mins = None
        if log.feed_cleanup_start and log.feed_cleanup_end:
            try:
                cleanup_duration_mins = calculate_feed_cleanup_duration(log.feed_cleanup_start, log.feed_cleanup_end)
            except Exception:
                pass
        feed_cleanup_hours = round(cleanup_duration_mins / 60.0, 1) if cleanup_duration_mins else None

        enriched_logs.append({
            'log': log,
            'stock_male': d.get('stock_male_prod_end', 0) + d.get('stock_male_hosp_end', 0),
            'stock_female': d.get('stock_female_prod_end', 0) + d.get('stock_female_hosp_end', 0),
            'lighting_hours': lighting_hours,
            'medications': meds_str,
            'egg_prod_pct': d['egg_prod_pct'],
            'total_feed': d['feed_total_kg'],
            'feed_cleanup_hours': feed_cleanup_hours,
            'egg_data': {
                'jumbo': d['cull_eggs_jumbo'],
                'jumbo_pct': d['cull_eggs_jumbo_pct'],
                'small': d['cull_eggs_small'],
                'small_pct': d['cull_eggs_small_pct'],
                'crack': d['cull_eggs_crack'],
                'crack_pct': d['cull_eggs_crack_pct'],
                'abnormal': d['cull_eggs_abnormal'],
                'abnormal_pct': d['cull_eggs_abnormal_pct'],
                'hatching': d['hatch_eggs'],
                'hatching_pct': d['hatch_egg_pct'],
                'total_culls': d['cull_eggs_total'],
                'total_culls_pct': d['cull_eggs_pct']
            }
        })

    # 2. Weekly Data (For Table)
    weekly_data = []
    for ws in weekly_stats:
        # Notes formatting
        note_str = " | ".join(ws['notes'])

        w_item = {
            'week': ws['week'],
            'mortality_male': ws['mortality_male'],
            'mortality_female': ws['mortality_female'],
            'culls_male': ws['culls_male'],
            'culls_female': ws['culls_female'],
            'eggs': ws['eggs_collected'],
            'hatch_eggs_sum': ws['hatch_eggs'],
            'cull_eggs_total': ws['cull_eggs_jumbo'] + ws['cull_eggs_small'] + ws['cull_eggs_crack'] + ws['cull_eggs_abnormal'],

            # Derived
            'mort_pct_m': ws['mortality_male_pct'],
            'mort_pct_f': ws['mortality_female_pct'],
            'cull_pct_m': ws['culls_male_pct'],
            'cull_pct_f': ws['culls_female_pct'],
            'egg_prod_pct': ws['egg_prod_pct'],
            'hatching_egg_pct': ws['hatch_egg_pct'],
            'cull_eggs_jumbo': ws['cull_eggs_jumbo'],
            'cull_eggs_jumbo_pct': ws['cull_eggs_jumbo_pct'] * 100 if ws.get('cull_eggs_jumbo_pct') else 0,
            'cull_eggs_small': ws['cull_eggs_small'],
            'cull_eggs_small_pct': ws['cull_eggs_small_pct'] * 100 if ws.get('cull_eggs_small_pct') else 0,
            'cull_eggs_crack': ws['cull_eggs_crack'],
            'cull_eggs_crack_pct': ws['cull_eggs_crack_pct'] * 100 if ws.get('cull_eggs_crack_pct') else 0,
            'cull_eggs_abnormal': ws['cull_eggs_abnormal'],
            'cull_eggs_abnormal_pct': ws['cull_eggs_abnormal_pct'] * 100 if ws.get('cull_eggs_abnormal_pct') else 0,

            'avg_bw_male': round_to_whole(ws['body_weight_male']),
            'avg_bw_female': round_to_whole(ws['body_weight_female']),

            # Additional for Charts
            'avg_bw_male_std': 0, # Placeholder if needed, or calc
            'avg_bw_female_std': 0,
            'avg_unif_male': ws['uniformity_male'],
            'avg_unif_female': ws['uniformity_female'],
            'partition_avgs': {}, # Not strictly used in table unless drilled down

            'notes': ws['notes'],
            'photos': ws['photos']
        }
        weekly_data.append(w_item)

    # 3. Chart Data (Daily)
    chart_data = {
        'dates': [d['date'].strftime('%Y-%m-%d') for d in daily_stats],
        'ages': [d['log'].age_week_day for d in daily_stats],
        'mortality_cum_male': [round(d['mortality_cum_male_pct'], 2) for d in daily_stats],
        'mortality_cum_female': [round(d['mortality_cum_female_pct'], 2) for d in daily_stats],
        'mortality_daily_male': [round(d['mortality_male_pct'], 2) for d in daily_stats],
        'mortality_daily_female': [round(d['mortality_female_pct'], 2) for d in daily_stats],
        'culls_daily_male': [round(d['culls_male_pct'], 2) for d in daily_stats],
        'culls_daily_female': [round(d['culls_female_pct'], 2) for d in daily_stats],
        'egg_prod': [round(d['egg_prod_pct'], 2) for d in daily_stats],
        'std_egg_prod': [round(d['std_egg_prod'], 2) for d in daily_stats],
        'hatch_egg_pct': [round(d['hatch_egg_pct'], 2) for d in daily_stats],
        'std_hatching_egg_pct': [round(d['std_hatching_egg_pct'], 2) for d in daily_stats],
        'cull_eggs_jumbo_pct': [round(d['cull_eggs_jumbo_pct'], 2) for d in daily_stats],
        'cull_eggs_small_pct': [round(d['cull_eggs_small_pct'], 2) for d in daily_stats],
        'cull_eggs_crack_pct': [round(d['cull_eggs_crack_pct'], 2) for d in daily_stats],
        'cull_eggs_abnormal_pct': [round(d['cull_eggs_abnormal_pct'], 2) for d in daily_stats],
        'male_ratio': [round(d['male_ratio_stock'], 2) if d['male_ratio_stock'] else 0 for d in daily_stats],
        'bw_male_std': [d['log'].standard_bw_male if d['log'].standard_bw_male > 0 else None for d in daily_stats],
        'bw_female_std': [d['log'].standard_bw_female if d['log'].standard_bw_female > 0 else None for d in daily_stats],
        'unif_male': [scale_pct(d['uniformity_male']) if d['uniformity_male'] > 0 else None for d in daily_stats],
        'unif_female': [scale_pct(d['uniformity_female']) if d['uniformity_female'] > 0 else None for d in daily_stats],

        # Raw BW for charts (None if 0)
        'bw_f': [d['body_weight_female'] if d['body_weight_female'] > 0 else None for d in daily_stats],
        'bw_m': [d['body_weight_male'] if d['body_weight_male'] > 0 else None for d in daily_stats],

        'water_per_bird': [round(d['water_per_bird'], 1) if d['water_per_bird'] >= 0 else None for d in daily_stats],
        'water_feed_ratio': [round(d.get('water_feed_ratio'), 2) if d.get('water_feed_ratio') is not None and d.get('water_feed_ratio') >= 0 else None for d in daily_stats],
        'feed_male_gp_bird': [round(d['feed_male_gp_bird'], 1) for d in daily_stats],
        'feed_female_gp_bird': [round(d['feed_female_gp_bird'], 1) for d in daily_stats],
        'flushing': [d['log'].flushing for d in daily_stats],

        # Legacy Partitions from Log
        'bw_male_p1': [d['log'].bw_male_p1 if d['log'].bw_male_p1 > 0 else None for d in daily_stats],
        'bw_male_p2': [d['log'].bw_male_p2 if d['log'].bw_male_p2 > 0 else None for d in daily_stats],
        'bw_female_p1': [d['log'].bw_female_p1 if d['log'].bw_female_p1 > 0 else None for d in daily_stats],
        'bw_female_p2': [d['log'].bw_female_p2 if d['log'].bw_female_p2 > 0 else None for d in daily_stats],
        'bw_female_p3': [d['log'].bw_female_p3 if d['log'].bw_female_p3 > 0 else None for d in daily_stats],
        'bw_female_p4': [d['log'].bw_female_p4 if d['log'].bw_female_p4 > 0 else None for d in daily_stats],

        'notes': [],
        'medication_active': [],
        'medication_names': []
    }
    
    # Fill dynamic partitions and notes
    for i in range(1, 9):
        chart_data[f'bw_M{i}'] = []
        chart_data[f'bw_F{i}'] = []

    for d in daily_stats:
        log = d['log']
        p_map = {pw.partition_name: pw.body_weight for pw in log.partition_weights}

        for i in range(1, 9):
            val_m = p_map.get(f'M{i}', 0)
            if val_m == 0 and i <= 2: val_m = getattr(log, f'bw_male_p{i}', 0)
            chart_data[f'bw_M{i}'].append(val_m if val_m > 0 else None)

            val_f = p_map.get(f'F{i}', 0)
            if val_f == 0 and i <= 4: val_f = getattr(log, f'bw_female_p{i}', 0)
            chart_data[f'bw_F{i}'].append(val_f if val_f > 0 else None)

        note_obj = None

        # Construct Note
        note_parts = []
        if log.flushing: note_parts.append("[FLUSHING]")
        if log.clinical_notes: note_parts.append(log.clinical_notes)

        # Meds
        active_meds = [m.drug_name for m in medications if m.start_date <= log.date and (m.end_date is None or m.end_date >= log.date)]
        chart_data['medication_active'].append(len(active_meds) > 0)
        chart_data['medication_names'].append(", ".join(active_meds) if active_meds else "")

        # User requested to remove medication from notes, so we don't append to note_parts
        # if active_meds: note_parts.append("Meds: " + ", ".join(active_meds))

        # Vacs
        done_vacs = [v.vaccine_name for v in vacs if v.actual_date == log.date]
        if done_vacs: note_parts.append("Vac: " + ", ".join(done_vacs))

        # Main Photos (note_id is None)
        main_photos = [p for p in log.photos if p.note_id is None]

        # Extra Notes
        extra_notes = []
        if log.clinical_notes_list:
            for n in log.clinical_notes_list:
                n_photos = []
                for p in n.photos:
                    n_photos.append({
                        'url': url_for('uploaded_file', filename=os.path.basename(p.file_path)),
                        'name': p.original_filename or 'Photo'
                    })
                extra_notes.append({
                    'caption': n.caption,
                    'photos': n_photos
                })

        has_any_data = (note_parts or main_photos or extra_notes)

        if has_any_data:
            main_photo_list = []
            for p in main_photos:
                main_photo_list.append({
                    'url': url_for('uploaded_file', filename=os.path.basename(p.file_path)),
                    'name': p.original_filename or 'Photo'
                })

            note_obj = {
                'note': " | ".join(note_parts), # Kept for backward compat in tooltips
                'main_note': " | ".join(note_parts),
                'main_photos': main_photo_list,
                'extra_notes': extra_notes,
                'photos': main_photo_list # Fallback for legacy views
            }

        chart_data['notes'].append(note_obj)

    # 4. Chart Data (Weekly)
    # Calculate Cumulative Mortality for Weekly points manually as metrics.py aggregates per week (independent sums)
    cum_mort_m_agg = 0
    cum_mort_f_agg = 0
    start_m = flock.intake_male or 1
    start_f = flock.intake_female or 1

    # Check if we are in production phase to use prod start?
    # metrics.py handles this per week if we query it right, but here we just iterate
    # Actually metrics.py `enrich` resets cum sum on phase switch.
    # We should grab the last cumulative value of the week from daily stats?
    # Yes, much safer. But daily stats are flattened.
    # Let's just sum up the weekly deaths.
    # NOTE: If phase switch happened mid-week, the cumulative logic is tricky.
    # But for charts, we usually want % of START stock.
    # Let's rely on standard logic: Cumulative deaths / Intake.
    # If Production, Cumulative deaths (since prod start) / Prod Start Stock.
    # This matches the behavior of daily charts.

    # We will assume Start Stock is global intake unless we detect phase shift logic?
    # metrics.py's enrich logic is best.
    # Let's just pick the last day of the week from daily_stats and take its cumulative %?
    # Yes! That's the most accurate representation of "End of Week Cumulative %".

    weekly_map = {ws['week']: ws for ws in weekly_stats}

    chart_data_weekly = {
        'dates': [],
        'mortality_cum_male': [], 'mortality_cum_female': [],
        'mortality_weekly_male': [], 'mortality_weekly_female': [],
        'culls_weekly_male': [], 'culls_weekly_female': [],
        'avg_bw_male': [], 'avg_bw_female': [],
        'egg_prod': [],
        'bw_male_std': [], 'bw_female_std': [],
        'unif_male': [], 'unif_female': [],
        'notes': []
    }
    for i in range(1, 9):
        chart_data_weekly[f'bw_M{i}'] = []
        chart_data_weekly[f'bw_F{i}'] = []

    # Group daily_stats by week to get end-of-week cum values
    daily_by_week = {}
    for d in daily_stats:
        if d['week'] not in daily_by_week: daily_by_week[d['week']] = []
        daily_by_week[d['week']].append(d)

    for w in sorted(weekly_map.keys()):
        ws = weekly_map[w]
        last_day = daily_by_week[w][-1]

        chart_data_weekly['dates'].append(f"Week {w}")
        chart_data_weekly['mortality_cum_male'].append(round(last_day['mortality_cum_male_pct'], 2))
        chart_data_weekly['mortality_cum_female'].append(round(last_day['mortality_cum_female_pct'], 2))

        chart_data_weekly['mortality_weekly_male'].append(round(ws['mortality_male_pct'], 2))
        chart_data_weekly['mortality_weekly_female'].append(round(ws['mortality_female_pct'], 2))
        chart_data_weekly['culls_weekly_male'].append(round(ws['culls_male_pct'], 2))
        chart_data_weekly['culls_weekly_female'].append(round(ws['culls_female_pct'], 2))

        chart_data_weekly['avg_bw_male'].append(round_to_whole(ws['body_weight_male']) if ws['body_weight_male'] > 0 else None)
        chart_data_weekly['avg_bw_female'].append(round_to_whole(ws['body_weight_female']) if ws['body_weight_female'] > 0 else None)

        chart_data_weekly['egg_prod'].append(round(ws['egg_prod_pct'], 2))
        chart_data_weekly['std_egg_prod'] = chart_data_weekly.get('std_egg_prod', [])
        chart_data_weekly['std_egg_prod'].append(round(ws['std_egg_prod'], 2))

        chart_data_weekly['hatch_egg_pct'] = chart_data_weekly.get('hatch_egg_pct', [])
        chart_data_weekly['hatch_egg_pct'].append(round(ws['hatch_egg_pct'], 2))

        chart_data_weekly['std_hatching_egg_pct'] = chart_data_weekly.get('std_hatching_egg_pct', [])
        chart_data_weekly['std_hatching_egg_pct'].append(round(ws['std_hatching_egg_pct'], 2))

        chart_data_weekly['cull_eggs_jumbo_pct'] = chart_data_weekly.get('cull_eggs_jumbo_pct', [])
        chart_data_weekly['cull_eggs_jumbo_pct'].append(round(ws['cull_eggs_jumbo_pct'], 2))

        chart_data_weekly['cull_eggs_small_pct'] = chart_data_weekly.get('cull_eggs_small_pct', [])
        chart_data_weekly['cull_eggs_small_pct'].append(round(ws['cull_eggs_small_pct'], 2))

        chart_data_weekly['cull_eggs_crack_pct'] = chart_data_weekly.get('cull_eggs_crack_pct', [])
        chart_data_weekly['cull_eggs_crack_pct'].append(round(ws['cull_eggs_crack_pct'], 2))

        chart_data_weekly['cull_eggs_abnormal_pct'] = chart_data_weekly.get('cull_eggs_abnormal_pct', [])
        chart_data_weekly['cull_eggs_abnormal_pct'].append(round(ws['cull_eggs_abnormal_pct'], 2))

        # Standard BW - Use Biological Age (w)
        std_bio = std_map.get(w)
        chart_data_weekly['bw_male_std'].append(std_bio.std_bw_male if std_bio and std_bio.std_bw_male > 0 else None)
        chart_data_weekly['bw_female_std'].append(std_bio.std_bw_female if std_bio and std_bio.std_bw_female > 0 else None)

        chart_data_weekly['unif_male'].append(scale_pct(ws['uniformity_male']) if ws['uniformity_male'] > 0 else None)
        chart_data_weekly['unif_female'].append(scale_pct(ws['uniformity_female']) if ws['uniformity_female'] > 0 else None)

        chart_data_weekly['water_per_bird'] = chart_data_weekly.get('water_per_bird', [])
        chart_data_weekly['water_per_bird'].append(round(ws['water_per_bird'], 1) if ws.get('water_per_bird', 0) >= 0 else None)
        chart_data_weekly['water_feed_ratio'] = chart_data_weekly.get('water_feed_ratio', [])
        chart_data_weekly['water_feed_ratio'].append(round(ws.get('water_feed_ratio'), 2) if ws.get('water_feed_ratio') is not None and ws.get('water_feed_ratio') >= 0 else None)

        chart_data_weekly['feed_male_gp_bird'] = chart_data_weekly.get('feed_male_gp_bird', [])
        chart_data_weekly['feed_male_gp_bird'].append(round(ws['feed_male_gp_bird'], 1))

        chart_data_weekly['feed_female_gp_bird'] = chart_data_weekly.get('feed_female_gp_bird', [])
        chart_data_weekly['feed_female_gp_bird'].append(round(ws['feed_female_gp_bird'], 1))

        # Aggregate Partitions for Weekly View
        def get_p_val(log, p_name, is_male, index):
             p_map = {pw.partition_name: pw.body_weight for pw in log.partition_weights}
             val = p_map.get(p_name, 0)
             if val == 0:
                 attr = f'bw_male_p{index}' if is_male else f'bw_female_p{index}'
                 if hasattr(log, attr):
                     val = getattr(log, attr, 0)
             return val

        for i in range(1, 9):
            m_key = f'M{i}'
            f_key = f'F{i}'
            m_vals = []
            f_vals = []

            for d in daily_by_week[w]:
                log = d['log']
                vm = get_p_val(log, m_key, True, i)
                if vm and vm > 0: m_vals.append(vm)
                vf = get_p_val(log, f_key, False, i)
                if vf and vf > 0: f_vals.append(vf)

            val_m = round(sum(m_vals)/len(m_vals)) if m_vals else None
            val_f = round(sum(f_vals)/len(f_vals)) if f_vals else None

            chart_data_weekly[f'bw_M{i}'].append(val_m)
            chart_data_weekly[f'bw_F{i}'].append(val_f)

        # Aggregate Weekly Notes/Photos
        week_notes = []
        week_photos = []

        # From Daily Logs
        if w in daily_by_week:
            week_logs_data = daily_by_week[w]
            if week_logs_data:
                w_start = week_logs_data[0]['date']
                w_end = week_logs_data[-1]['date']

                for d in week_logs_data:
                    log = d['log']
                    if log.clinical_notes:
                        week_notes.append(f"{log.date.strftime('%d/%m')}: {log.clinical_notes}")

                    for p in log.photos:
                        week_photos.append({
                            'url': url_for('uploaded_file', filename=os.path.basename(p.file_path)),
                            'name': f"{log.date.strftime('%d/%m')} {p.original_filename or 'Photo'}"
                        })

                # Meds
                w_meds = set()
                for m in medications:
                    if m.start_date <= w_end and (m.end_date is None or m.end_date >= w_start):
                        w_meds.add(m.drug_name)
                if w_meds: week_notes.append("Meds: " + ", ".join(w_meds))

                # Vacs
                w_vacs = set()
                for v in vacs:
                    if v.actual_date and w_start <= v.actual_date <= w_end:
                        w_vacs.add(v.vaccine_name)
                if w_vacs: week_notes.append("Vac: " + ", ".join(w_vacs))

        if week_notes or week_photos:
            chart_data_weekly['notes'].append({
                'note': " | ".join(week_notes),
                'photos': week_photos
            })
        else:
            chart_data_weekly['notes'].append(None)

    # Legacy keys for weekly
    chart_data_weekly['bw_male_p1'] = chart_data_weekly['bw_M1']
    chart_data_weekly['bw_male_p2'] = chart_data_weekly['bw_M2']
    chart_data_weekly['bw_female_p1'] = chart_data_weekly['bw_F1']
    chart_data_weekly['bw_female_p2'] = chart_data_weekly['bw_F2']
    chart_data_weekly['bw_female_p3'] = chart_data_weekly['bw_F3']
    chart_data_weekly['bw_female_p4'] = chart_data_weekly['bw_F4']

    # 5. Current Stats (Stock at end of last processed log)
    if daily_stats:
        last = daily_stats[-1]

        current_stats = {
            'male_prod': last.get('stock_male_prod_end', 0),
            'female_prod': last.get('stock_female_prod_end', 0),
            'male_hosp': last.get('stock_male_hosp_end', 0),
            'female_hosp': last.get('stock_female_hosp_end', 0),
            'male_ratio': last['male_ratio_stock'] if last.get('male_ratio_stock') else 0
        }
    else:
        current_stats = {
            'male_prod': flock.intake_male,
            'female_prod': flock.intake_female,
            'male_hosp': 0,
            'female_hosp': 0,
            'male_ratio': (flock.intake_male / flock.intake_female * 100) if flock.intake_female > 0 else 0
        }

    weekly_data.reverse()

    # Pre-check available reports for this flock
    from werkzeug.utils import secure_filename
    reports_dir = os.path.join(app.root_path, 'static', 'reports')
    available_reports = set()
    if os.path.exists(reports_dir):
        # We need a quick way to know which dates have reports
        prefix_to_match = f"_{secure_filename(flock.house.name)}_"
        for f in os.listdir(reports_dir):
            if prefix_to_match in f and f.endswith(".jpg"):
                date_str = f.split("_")[0]
                available_reports.add(date_str)

    return render_template('flock_detail_modern.html', flock=flock, logs=list(reversed(enriched_logs)), weekly_data=weekly_data, chart_data=chart_data, chart_data_weekly=chart_data_weekly, current_stats=current_stats, global_std=gs, active_flocks=active_flocks, summary_dashboard=summary_dashboard, summary_table=summary_table, health_events=health_events, available_reports=available_reports)

@app.route('/flock/<int:id>/spreadsheet')
@login_required
@dept_required('Farm')
def flock_spreadsheet(id):
    if not current_user.role == 'Admin':
        flash('Access Denied: Admin only.', 'danger')
        return redirect(url_for('view_flock', id=id))

    flock = db.session.get(Flock, id)
    if not flock:
        flash('Flock not found', 'danger')
        return redirect(url_for('index'))

    # Load all logs for this flock
    logs = DailyLog.query.options(joinedload(DailyLog.partition_weights), joinedload(DailyLog.photos), joinedload(DailyLog.clinical_notes_list)).filter_by(flock_id=id).order_by(DailyLog.date.asc()).all()

    # Enrich with standards (for benchmarks)
    standards_list = Standard.query.all()
    standards_by_week = {getattr(s, 'week'): s for s in standards_list if hasattr(s, 'week')}
    standards_by_prod_week = {s.production_week: s for s in standards_list}

    # Fetch Global Standard for hatching egg %
    gs = GlobalStandard.query.first()
    std_hatching_egg_pct = gs.std_hatching_egg_pct if gs and gs.std_hatching_egg_pct is not None else 96.0

    # Fetch Feed Codes
    feed_codes = FeedCode.query.order_by(FeedCode.code.asc()).all()
    feed_code_options = [fc.code for fc in feed_codes]

    spreadsheet_data = []

    spreadsheet_data = generate_spreadsheet_data(flock, logs, standards_by_week, standards_by_prod_week)

    return render_template('flock_spreadsheet_modern.html', flock=flock, spreadsheet_data=spreadsheet_data, feed_codes=feed_code_options)

def generate_spreadsheet_data(flock, logs, standards_by_week, standards_by_prod_week):
    spreadsheet_data = []
    from metrics import enrich_flock_data
    flock_logs = [l for l in logs]
    enriched = enrich_flock_data(flock, flock_logs)

    for item in enriched:
        log = item['log']
        week = item['week']
        prod_week = item['production_week']

        bio_std = standards_by_week.get(week)
        prod_std = standards_by_prod_week.get(prod_week)

        notes_parts = []
        if log.clinical_notes:
            notes_parts.append(log.clinical_notes)

        list_notes = [note.caption for note in log.clinical_notes_list if note.caption]
        if list_notes:
            notes_parts.extend(list_notes)

        clinical_notes_str = ', '.join(notes_parts)

        # Get partition weights
        p_map = {pw.partition_name: pw.body_weight for pw in log.partition_weights}
        p_uni_map = {pw.partition_name: pw.uniformity for pw in log.partition_weights}

        row_data = [
            log.id,
            log.date.strftime('%Y-%m-%d'),
            item['age_days'],
            clinical_notes_str,
            log.mortality_male,
            log.mortality_female,
            log.mortality_male_hosp,
            log.mortality_female_hosp,
            log.culls_male,
            log.culls_female,
            log.culls_male_hosp,
            log.culls_female_hosp,
            log.males_moved_to_hosp,
            log.females_moved_to_hosp,
            log.males_moved_to_prod,
            log.females_moved_to_prod,
            log.feed_program,
            log.feed_code_male.code if log.feed_code_male else '',
            log.feed_code_female.code if log.feed_code_female else '',
            log.feed_male_gp_bird,
            log.feed_female_gp_bird,
            log.feed_cleanup_start,
            log.feed_cleanup_end,
            log.water_reading_1,
            log.water_reading_2,
            log.water_reading_3,
            True if log.flushing else False,
            log.eggs_collected,
            log.egg_weight,
            log.cull_eggs_jumbo,
            log.cull_eggs_small,
            log.cull_eggs_abnormal,
            log.cull_eggs_crack,
            True if log.is_weighing_day else False,
            log.body_weight_male,
            log.body_weight_female,
            log.uniformity_male,
            log.uniformity_female,
            log.standard_bw_male,
            log.standard_bw_female
        ]

        # Add partitions
        for i in range(1, 9):
            row_data.append(p_map.get(f'M{i}', getattr(log, f'bw_male_p{i}', None) if i <= 2 else None))
            row_data.append(p_uni_map.get(f'M{i}', getattr(log, f'unif_male_p{i}', None) if i <= 2 else None))
        for i in range(1, 9):
            row_data.append(p_map.get(f'F{i}', getattr(log, f'bw_female_p{i}', None) if i <= 4 else None))
            row_data.append(p_uni_map.get(f'F{i}', getattr(log, f'unif_female_p{i}', None) if i <= 4 else None))

        row_data.extend([
            log.light_on_time,
            log.light_off_time,
            bio_std.std_mortality_female if bio_std else 0, # Benchmark Female Mort
            prod_std.std_egg_prod if prod_std else 0,       # Benchmark Egg Prod
            bio_std.std_bw_male if bio_std else 0,        # Benchmark
            bio_std.std_bw_female if bio_std else 0       # Benchmark
        ])

        spreadsheet_data.append(row_data)

    return spreadsheet_data

@app.route('/api/flock/<int:flock_id>/export_csv')
def export_flock_csv(flock_id):
    # Both Farm and Executive roles can view flock details, so both should be able to export
    if not current_user.role == 'Admin' and current_user.role not in ALLOWED_EXPORT_ROLES:
        flash('Access Denied.', 'danger')
        return redirect(url_for('index'))

    flock = db.session.get(Flock, flock_id)
    if not flock:
        flash('Flock not found', 'danger')
        return redirect(url_for('index'))

    # Load all logs for this flock
    logs = DailyLog.query.options(joinedload(DailyLog.partition_weights), joinedload(DailyLog.photos), joinedload(DailyLog.clinical_notes_list)).filter_by(flock_id=flock_id).order_by(DailyLog.date.asc()).all()

    # Enrich with standards (for benchmarks)
    standards_list = Standard.query.all()
    standards_by_week = {getattr(s, 'week'): s for s in standards_list if hasattr(s, 'week')}
    standards_by_prod_week = {s.production_week: s for s in standards_list}

    spreadsheet_data = generate_spreadsheet_data(flock, logs, standards_by_week, standards_by_prod_week)

    headers = [
        "ID", "Date", "Age (Days)", "Clinical Signs",
        "Mortality (M)", "Mortality (F)", "Hosp Mort (M)", "Hosp Mort (F)",
        "Culls (M)", "Culls (F)", "Hosp Culls (M)", "Hosp Culls (F)",
        "Moved to Hosp (M)", "Moved to Hosp (F)", "Moved to Prod (M)", "Moved to Prod (F)",
        "Feed Program", "Feed Code (M)", "Feed Code (F)",
        "Feed (g/bird M)", "Feed (g/bird F)", "Feed Cleanup Start", "Feed Cleanup End",
        "Water 1", "Water 2", "Water 3", "Flushing",
        "Eggs Collected", "Egg Weight", "Eggs Jumbo", "Eggs Small", "Eggs Abnormal", "Eggs Crack",
        "Weighing Day", "Avg BW (M)", "Avg BW (F)", "Avg Unif (M)", "Avg Unif (F)", "Std BW (M)", "Std BW (F)"
    ]

    for i in range(1, 9):
        headers.extend([f"M{i} BW", f"M{i} Unif"])
    for i in range(1, 9):
        headers.extend([f"F{i} BW", f"F{i} Unif"])

    headers.extend([
        "Light On", "Light Off",
        "Std Mort %", "Std Egg Prod %", "Std BW (M) Bench", "Std BW (F) Bench"
    ])

    import io
    import csv
    from flask import Response

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in spreadsheet_data:
        writer.writerow(row)

    response = Response(output.getvalue(), mimetype='text/csv')
    response.headers["Content-Disposition"] = f"attachment; filename=flock_{flock_id}_raw_data.csv"
    return response

@app.route('/api/flock/<int:flock_id>/spreadsheet_save', methods=['POST'])
def flock_spreadsheet_save(flock_id):
    if not current_user.role == 'Admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    data = request.json.get('data', [])
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    try:
        # Pre-fetch Feed Codes
        feed_codes = FeedCode.query.all()
        feed_code_map = {fc.code: fc.id for fc in feed_codes}

        # Fetch logs mapped by ID
        log_ids = [row.get('id') for row in data if row.get('id')]
        logs = {log.id: log for log in DailyLog.query.filter(DailyLog.id.in_(log_ids), DailyLog.flock_id == flock_id).all()}

        # Fetch all existing logs for new row existence checks to avoid N+1 query
        new_row_dates = []
        for row in data:
            if not row.get('id') and row.get('date'):
                try:
                    parsed_date = datetime.strptime(row.get('date'), '%Y-%m-%d').date()
                    new_row_dates.append(parsed_date)
                except ValueError:
                    continue

        existing_logs_by_date = {}
        if new_row_dates:
            existing_logs_by_date = {log.date: log for log in DailyLog.query.filter(DailyLog.date.in_(new_row_dates), DailyLog.flock_id == flock_id).all()}

        flock = Flock.query.get(flock_id)
        if not flock:
            return jsonify({'success': False, 'error': 'Flock not found'}), 404

        for row in data:
            log_id = row.get('id')
            is_new = False
            if not log_id:
                # Handle new row
                date_str = row.get('date')
                if not date_str:
                    continue
                try:
                    log_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                except ValueError:
                    continue

                # Check if it exists
                log = existing_logs_by_date.get(log_date)
                if not log:
                    log = DailyLog(
                        flock_id=flock_id,
                        date=log_date,                        body_weight_male=0,
                        body_weight_female=0
                    )
                    db.session.add(log)
                    existing_logs_by_date[log_date] = log
                    is_new = True
            else:
                try:
                    log_id_int = int(log_id)
                except (ValueError, TypeError):
                    continue
                if log_id_int not in logs:
                    continue
                log = logs[log_id_int]

            old_data = {}

            # Update fields
            numeric_fields = [
                'mortality_male', 'mortality_female', 'mortality_male_hosp', 'mortality_female_hosp',
                'culls_male', 'culls_female', 'culls_male_hosp', 'culls_female_hosp',
                'males_moved_to_hosp', 'females_moved_to_hosp', 'males_moved_to_prod', 'females_moved_to_prod',
                'water_reading_1', 'water_reading_2', 'water_reading_3',
                'eggs_collected', 'cull_eggs_jumbo', 'cull_eggs_small', 'cull_eggs_abnormal', 'cull_eggs_crack'
            ]

            float_fields = [
                'feed_male_gp_bird', 'feed_female_gp_bird', 'egg_weight',
                'body_weight_male', 'body_weight_female', 'uniformity_male', 'uniformity_female',
                'standard_bw_male', 'standard_bw_female'
            ]

            string_fields = [
                'feed_program', 'feed_cleanup_start', 'feed_cleanup_end', 'light_on_time', 'light_off_time'
            ]

            boolean_fields = [
                'flushing', 'is_weighing_day'
            ]

            for field in numeric_fields:
                if not is_new: old_data[field] = getattr(log, field)
                val = row.get(field)
                if val == '': val = 0
                if val is not None:
                    try: val = int(float(val))
                    except ValueError: val = 0
                else: val = 0
                setattr(log, field, val)

            for field in float_fields:
                if not is_new: old_data[field] = getattr(log, field)
                val = row.get(field)
                if val == '': val = 0.0
                if val is not None:
                    try: val = float(val)
                    except ValueError: val = 0.0
                else: val = 0.0
                setattr(log, field, val)

            for field in string_fields:
                if not is_new: old_data[field] = getattr(log, field)
                val = row.get(field)
                setattr(log, field, val if val else None)

            for field in boolean_fields:
                if not is_new: old_data[field] = getattr(log, field)
                val = row.get(field)
                if isinstance(val, str):
                    val = val.lower() == 'true'
                setattr(log, field, bool(val))

            # Calculate feed totals based on g/bird and current stock
            # We must use start-of-day stock.
            # In recalculate_flock_inventory, we'll recompute the stock properly.
            # However, for now, we can rely on log.males_at_start if it exists or use fallback.
            start_m = log.males_at_start or 0
            start_f = log.females_at_start or 0

            multiplier = 1.0
            if log.feed_program == 'Skip-a-day':
                multiplier = 2.0
            elif log.feed_program == '2/1':
                multiplier = 1.5

            # Handle Feed Code mapping for Male
            fc_m_code = row.get('feed_code_male')
            if fc_m_code and fc_m_code in feed_code_map:
                log.feed_code_male_id = feed_code_map[fc_m_code]
            else:
                log.feed_code_male_id = None

            fc_f_code = row.get('feed_code_female')
            if fc_f_code and fc_f_code in feed_code_map:
                log.feed_code_female_id = feed_code_map[fc_f_code]
            else:
                log.feed_code_female_id = None

            # Handle clinical signs
            if not is_new: old_data['clinical_notes'] = log.clinical_notes
            clinical_signs_val = row.get('clinical_signs')

            # Since ClinicalNote model list represents detailed notes and clinical_notes text is main note:
            if clinical_signs_val and clinical_signs_val.strip() and clinical_signs_val.strip().lower() not in EMPTY_NOTE_VALUES:
                log.clinical_notes = clinical_signs_val.strip()
            else:
                log.clinical_notes = None

            # Handle Partitions
            if log.id:
                PartitionWeight.query.filter_by(log_id=log.id).delete()
            else:
                db.session.flush() # Get log.id

            sum_bw_m = 0; count_bw_m = 0
            sum_uni_m = 0; count_uni_m = 0
            sum_bw_f = 0; count_bw_f = 0
            sum_uni_f = 0; count_uni_f = 0

            for i in range(1, 9):
                # Male partitions
                p_m_bw = row.get(f'bw_M{i}')
                p_m_uni = row.get(f'uni_M{i}')
                try: p_m_bw = int(float(p_m_bw)) if p_m_bw else 0
                except: p_m_bw = 0
                try: p_m_uni = float(p_m_uni) if p_m_uni else 0.0
                except: p_m_uni = 0.0

                if p_m_bw > 0:
                    pw_m = PartitionWeight(log_id=log.id, partition_name=f'M{i}', body_weight=p_m_bw, uniformity=p_m_uni)
                    db.session.add(pw_m)
                    sum_bw_m += p_m_bw
                    count_bw_m += 1
                    if p_m_uni > 0:
                        sum_uni_m += p_m_uni
                        count_uni_m += 1

                # Female partitions
                p_f_bw = row.get(f'bw_F{i}')
                p_f_uni = row.get(f'uni_F{i}')
                try: p_f_bw = int(float(p_f_bw)) if p_f_bw else 0
                except: p_f_bw = 0
                try: p_f_uni = float(p_f_uni) if p_f_uni else 0.0
                except: p_f_uni = 0.0

                if p_f_bw > 0:
                    pw_f = PartitionWeight(log_id=log.id, partition_name=f'F{i}', body_weight=p_f_bw, uniformity=p_f_uni)
                    db.session.add(pw_f)
                    sum_bw_f += p_f_bw
                    count_bw_f += 1
                    if p_f_uni > 0:
                        sum_uni_f += p_f_uni
                        count_uni_f += 1

            # Auto calculate average if not provided but partitions exist
            if log.body_weight_male == 0 and count_bw_m > 0:
                log.body_weight_male = round_to_whole(sum_bw_m / count_bw_m)
            if log.body_weight_female == 0 and count_bw_f > 0:
                log.body_weight_female = round_to_whole(sum_bw_f / count_bw_f)
            if log.uniformity_male == 0.0 and count_uni_m > 0:
                log.uniformity_male = sum_uni_m / count_uni_m
            if log.uniformity_female == 0.0 and count_uni_f > 0:
                log.uniformity_female = sum_uni_f / count_uni_f

            if not is_new:
                new_data = {}
                for field in numeric_fields + float_fields + string_fields + boolean_fields:
                    new_data[field] = getattr(log, field)
                new_data['clinical_notes'] = log.clinical_notes
                new_data['feed_code_male'] = log.feed_code_male.code if log.feed_code_male else ''
                new_data['feed_code_female'] = log.feed_code_female.code if log.feed_code_female else ''

                changes = {k: {'old': old_data[k], 'new': new_data[k]} for k in old_data if old_data[k] != new_data.get(k)}
                if changes:
                    log_user_activity(current_user.id, 'Edit', 'DailyLog', log.id, details=changes)
            else:
                log_user_activity(current_user.id, 'Add', 'DailyLog', log.id, details={'date': str(log.date)})

        safe_commit()

        # Recalculate inventory cascading after bulk save
        recalculate_flock_inventory(flock_id)

        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/flock/<int:id>/charts')
@login_required
@dept_required('Farm')
def flock_charts(id):
    flock = Flock.query.options(joinedload(Flock.house)).filter_by(id=id).first_or_404()
    return render_template('flock_charts.html', flock=flock)

@app.route('/flock/<int:id>/sampling')
@login_required
@dept_required('Farm')
def flock_sampling(id):
    flock = Flock.query.options(joinedload(Flock.house)).filter_by(id=id).first_or_404()
    events = SamplingEvent.query.filter_by(flock_id=id).order_by(SamplingEvent.age_week.asc()).all()
    return render_template('flock_sampling.html', flock=flock, events=events)

@app.route('/flock/<int:id>/vaccines', methods=['GET', 'POST'])
@login_required
@dept_required('Farm')
def flock_vaccines(id):
    flock = Flock.query.options(joinedload(Flock.house)).filter_by(id=id).first_or_404()
    if request.method == 'POST':
        if 'load_standard' in request.form:
            if Vaccine.query.filter_by(flock_id=id).count() == 0:
                initialize_vaccine_schedule(id)
                flash('Standard schedule loaded.', 'success')
            else:
                flash('Schedule is not empty. Cannot load standard.', 'warning')

        elif 'add_row' in request.form:
            v = Vaccine(flock_id=id, age_code='', vaccine_name='')
            db.session.add(v)
            safe_commit()
            flash('New row added.', 'success')

        elif 'delete_id' in request.form:
            v_id = request.form.get('delete_id')
            v = Vaccine.query.get(v_id)
            if v and v.flock_id == id:
                db.session.delete(v)
                safe_commit()
                flash('Record deleted.', 'info')

        elif 'save_changes' in request.form:
            # Bulk Update
            vaccine_ids = [k.split('_')[2] for k in request.form.keys() if k.startswith('v_id_')]
            updated_count = 0

            # Pre-fetch stock history for calculation
            stock_history = get_flock_stock_history(id)
            sorted_dates = sorted([d for d in stock_history.keys() if isinstance(d, date)])

            # Batch fetch vaccines
            vaccines = Vaccine.query.filter(Vaccine.id.in_(vaccine_ids)).all()
            vaccine_dict = {v.id: v for v in vaccines if v.flock_id == id}

            # Batch fetch inventory items
            unique_inv_ids = set()
            for vid in vaccine_ids:
                inv_id_val = request.form.get(f'v_inv_{vid}')
                if inv_id_val and inv_id_val.isdigit():
                    unique_inv_ids.add(int(inv_id_val))

            inventory_items_dict = {}
            if unique_inv_ids:
                items = InventoryItem.query.filter(InventoryItem.id.in_(unique_inv_ids)).all()
                inventory_items_dict = {item.id: item for item in items}

            for vid in vaccine_ids:
                v = vaccine_dict.get(int(vid)) if str(vid).isdigit() else None
                if not v: continue

                was_completed = v.actual_date is not None

                age_code = request.form.get(f'age_code_{vid}')

                # Handle Inventory
                inv_id_val = request.form.get(f'v_inv_{vid}')
                if inv_id_val and inv_id_val.isdigit():
                    v.inventory_item_id = int(inv_id_val)
                    item = inventory_items_dict.get(v.inventory_item_id)
                    if item: v.vaccine_name = item.name

                route = request.form.get(f'route_{vid}')
                est_date_str = request.form.get(f'est_date_{vid}')
                actual_date_str = request.form.get(f'actual_date_{vid}')
                remarks = request.form.get(f'remarks_{vid}')

                try:
                    dpu = int(request.form.get(f'doses_per_unit_{vid}') or 1000)
                    if not v.inventory_item_id:
                        v.doses_per_unit = dpu
                except: pass

                if age_code is not None: v.age_code = age_code
                if route is not None: v.route = route
                if remarks is not None: v.remarks = remarks

                if est_date_str:
                    try:
                        v.est_date = datetime.strptime(est_date_str, '%Y-%m-%d').date()
                    except ValueError: pass

                new_actual_date = None
                if actual_date_str:
                    try:
                        new_actual_date = datetime.strptime(actual_date_str, '%Y-%m-%d').date()
                        v.actual_date = new_actual_date
                    except ValueError: pass
                elif actual_date_str == '':
                    v.actual_date = None

                # Deduction Logic
                if new_actual_date and not was_completed and v.inventory_item_id:
                    # Calculate Units
                    target_date = v.est_date or date.today()
                    applicable_stock = flock.intake_male + flock.intake_female
                    best_date = None
                    for d in sorted_dates:
                        if d <= target_date: best_date = d
                        else: break
                    if best_date: applicable_stock = stock_history[best_date]

                    units = v.units_needed(applicable_stock)
                    if units > 0:
                        inv_item = inventory_items_dict.get(v.inventory_item_id)
                        if inv_item:
                            inv_item.current_stock -= units
                            t = InventoryTransaction(
                                inventory_item_id=v.inventory_item_id,
                                transaction_type='Usage',
                                quantity=units,
                                transaction_date=new_actual_date,
                                notes=f'Vaccine completed: {flock.flock_id} (Age {v.age_code})'
                            )
                            db.session.add(t)

                updated_count += 1

            safe_commit()
            flash(f'Updated {updated_count} records.', 'success')

        return redirect(url_for('flock_vaccines', id=id))

    vaccines = Vaccine.query.filter_by(flock_id=id).order_by(Vaccine.est_date.asc(), Vaccine.id.asc()).all()

    # Enrich with calculated data
    stock_history = get_flock_stock_history(id)
    default_stock = flock.intake_male + flock.intake_female

    for v in vaccines:
        # Stock at est_date
        stock = default_stock
        if v.est_date:
            stock = stock_history.get(v.est_date, stock_history.get('latest', default_stock))
            # If est_date is before first log, use intake?
            # get_flock_stock_history logic handles ranges implicitly by returning values for known log dates.
            # If est_date is NOT in keys (no log for that specific date), we should find the nearest previous date.
            # Since get_flock_stock_history returns only log dates, we need better lookup.

            # Improvement: get_flock_stock_history returns discrete points.
            # We need "Stock at Date X".
            # Simple lookup:
            #   Find max date in history <= est_date.

            # Let's do simple search here since N=500 logs is small.
            # Actually stock_history is dict.
            # Optimization: Sort keys once.
            pass

    # Re-implement enrichment with efficient lookup
    sorted_dates = sorted([d for d in stock_history.keys() if isinstance(d, date)])

    for v in vaccines:
        target_date = v.est_date or date.today()

        # Find applicable stock
        # Stock is valid for the day of log and subsequent days until next log?
        # Actually DailyLog records mortality for that day.
        # "Start of Day Stock" for Date X is: Intake - (Mortality BEFORE X).
        # My get_flock_stock_history returns "Start of Day Stock" for each log date.

        # If target_date matches a log date, use it.
        # If not, find the last log date < target_date.
        # If target_date < first log, use Intake.

        applicable_stock = flock.intake_male + flock.intake_female

        # Binary search or linear scan (dates are sorted)
        # Find largest d <= target_date
        best_date = None
        for d in sorted_dates:
            if d <= target_date:
                best_date = d
            else:
                break

        if best_date:
            applicable_stock = stock_history[best_date]
            # If best_date is exactly target_date, stock_history[best_date] is Start of Day stock. Correct.
            # If best_date < target_date, stock_history[best_date] is start of that day.
            # We should subtract mortality OF best_date and subsequent days?
            # get_flock_stock_history returns start of day stock.
            # If we have a gap, stock remains same? Yes, assuming no mortality on missing days.

            # However, if best_date < target_date, we need to subtract mortality of best_date itself to get end of day?
            # Actually, if logs are contiguous, we would have found a closer date.
            # If logs have gaps (missing data), we assume stock stays same.
            # But wait, stock_history[best_date] is stock at morning of best_date.
            # If target_date > best_date, birds might have died on best_date.
            # Effectively, we should use "End of Day" stock of best_date?
            # For simplicity/safety (overestimate), Start of Day stock of last known log is fine.
            pass

        v.calculated_dose_count = v.dose_count(applicable_stock)
        v.calculated_units_needed = v.units_needed(applicable_stock)

    return render_template('flock_vaccines.html', flock=flock, vaccines=vaccines)

@app.route('/vaccine_schedule')
def global_vaccine_schedule():
    import calendar
    today = date.today()

    try:
        year = int(request.args.get('year', today.year))
        month = int(request.args.get('month', today.month))
    except:
        year = today.year
        month = today.month

    cal = calendar.Calendar(firstweekday=6)
    month_days = cal.monthdatescalendar(year, month)

    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    start_date = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end_date = date(year, month, last_day)

    active_flocks = Flock.query.options(joinedload(Flock.house)).filter_by(status='Active').all()
    flock_ids = [f.id for f in active_flocks]

    vaccines = Vaccine.query.filter(Vaccine.flock_id.in_(flock_ids)).filter(Vaccine.est_date >= start_date, Vaccine.est_date <= end_date).order_by(Vaccine.est_date).all()

    events_by_date = {}
    for v in vaccines:
        d = v.est_date
        if d not in events_by_date: events_by_date[d] = []
        events_by_date[d].append(v)

    return render_template('vaccine_schedule.html',
                           year=year, month=month,
                           month_name=calendar.month_name[month],
                           month_days=month_days,
                           events_by_date=events_by_date,
                           prev_month=prev_month, prev_year=prev_year,
                           next_month=next_month, next_year=next_year,
                           today=today)

@app.route('/flock/<int:id>/sampling/<int:event_id>/upload', methods=['POST'])
@login_required
@dept_required('Farm')
def upload_sampling_result(id, event_id):
    event = SamplingEvent.query.get_or_404(event_id)

    remarks = request.form.get('remarks')
    if remarks:
        event.remarks = remarks

    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename != '':
            if file.filename.lower().endswith('.pdf'):
                filename = secure_filename(f"{event.flock.flock_id}_W{event.age_week}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                event.result_file = filepath
                event.upload_date = date.today()
                event.status = 'Completed'
                safe_commit()
                flash('Result uploaded successfully.', 'success')
            else:
                flash('Only PDF files are allowed.', 'danger')

    if remarks and not ('file' in request.files and request.files['file'].filename != ''):
        safe_commit()
        flash('Remarks updated.', 'success')

    return redirect(url_for('flock_sampling', id=id))


@app.route('/flock/<int:id>/hatchability', methods=['GET', 'POST'])
def flock_hatchability(id):
    if current_user.dept not in FARM_HATCHERY_ADMIN_DEPTS:
        flash("Access Denied.", "danger")
        return redirect(url_for('login'))

    flock = Flock.query.options(joinedload(Flock.house)).filter_by(id=id).first_or_404()
    if request.method == 'POST':
        if current_user.dept == 'Farm':
            flash("Farm users have read-only access to Hatchability.", "warning")
            return redirect(url_for('flock_hatchability', id=id))

        action = request.form.get('action')
        if action == 'add':
            try:
                setting_date = datetime.strptime(request.form.get('setting_date'), '%Y-%m-%d').date()
                candling_date = datetime.strptime(request.form.get('candling_date'), '%Y-%m-%d').date()
                hatching_date = datetime.strptime(request.form.get('hatching_date'), '%Y-%m-%d').date()

                # Pre-fetch for optimization before ratio calculation
                logs = DailyLog.query.filter_by(flock_id=flock.id).order_by(DailyLog.date).all()
                hatchery_records = Hatchability.query.filter_by(flock_id=flock.id).order_by(Hatchability.setting_date).all()

                # Calculate Male Ratio
                male_ratio, large_window = calculate_male_ratio(flock.id, setting_date, flock_obj=flock, logs=logs, hatchery_records=hatchery_records)

                h = Hatchability(
                    flock_id=flock.id,
                    setting_date=setting_date,
                    candling_date=candling_date,
                    hatching_date=hatching_date,
                    egg_set=int(request.form.get('egg_set') or 0),
                    clear_eggs=int(request.form.get('clear_eggs') or 0),
                    rotten_eggs=int(request.form.get('rotten_eggs') or 0),
                    hatched_chicks=int(request.form.get('hatched_chicks') or 0),
                    male_ratio_pct=male_ratio
                )
                db.session.add(h)
                db.session.flush()

                log_user_activity(current_user.id, 'Add', 'Hatchability', h.id, details={'flock_id': flock.flock_id, 'setting_date': setting_date.strftime('%Y-%m-%d')})

                safe_commit()

                msg = (
                    "Hatchability record added."
                    f"{' Note: Large collection window detected. Average Male Ratio may be affected.' if large_window else ''}"
                )
                flash(msg, 'success' if not large_window else 'warning')
            except ValueError as e:
                flash(f'Error adding record: {e}', 'danger')

        return redirect(url_for('flock_hatchability', id=id))

    records = Hatchability.query.filter_by(flock_id=id).order_by(Hatchability.setting_date.desc()).all()
    return render_template('flock_hatchability.html', flock=flock, records=records)

@app.route('/flock/<int:id>/hatchability/delete/<int:record_id>', methods=['POST'])
@login_required
@dept_required('Hatchery')
def delete_hatchability(id, record_id):
    record = Hatchability.query.get_or_404(record_id)
    if record.flock_id != id:
        return "Unauthorized", 403

    date_str = record.setting_date.strftime('%Y-%m-%d')
    log_user_activity(current_user.id, 'Delete', 'Hatchability', record_id, details={'flock_id': record.flock.flock_id, 'setting_date': date_str})

    db.session.delete(record)
    safe_commit()
    flash('Record deleted.', 'info')
    return redirect(url_for('flock_hatchability', id=id))

@app.route('/hatchery/charts/<int:flock_id>')
def hatchery_charts(flock_id):
    if current_user.dept not in FARM_HATCHERY_ADMIN_DEPTS:
        flash("Access Denied.", "danger")
        return redirect(url_for('login'))

    flock = Flock.query.get_or_404(flock_id)
    records = Hatchability.query.filter_by(flock_id=flock_id).order_by(Hatchability.setting_date.asc()).all()

    # Fetch Standards for Hatchability
    all_standards = Standard.query.all()
    std_map = {getattr(s, 'week'): (getattr(s, 'std_hatchability', 0.0) or 0.0) for s in all_standards if hasattr(s, 'week')}

    data = {
        'weeks': [],
        'fertile_pct': [],
        'clear_pct': [],
        'rotten_pct': [],
        'hatch_pct': [],
        'std_hatch_pct': [],
        'male_ratio_pct': [],
        'notes': []
    }

    # Aggregate by week
    weekly_agg = {}

    for r in records:
        age_days = (r.setting_date - flock.intake_date).days
        week = 0 if age_days == 0 else ((age_days - 1) // 7) + 1 if age_days > 0 else (age_days // 7)

        if week not in weekly_agg:
            weekly_agg[week] = {
                'egg_set': 0, 'clear_eggs': 0, 'rotten_eggs': 0, 'hatched_chicks': 0,
                'male_ratios': []
            }

        weekly_agg[week]['egg_set'] += (r.egg_set or 0)
        weekly_agg[week]['clear_eggs'] += (r.clear_eggs or 0)
        weekly_agg[week]['rotten_eggs'] += (r.rotten_eggs or 0)
        weekly_agg[week]['hatched_chicks'] += (r.hatched_chicks or 0)

        if r.male_ratio_pct is not None:
            weekly_agg[week]['male_ratios'].append(r.male_ratio_pct)

    sorted_weeks = sorted(weekly_agg.keys())

    for week in sorted_weeks:
        agg = weekly_agg[week]

        # Standard Lookup
        std_val = std_map.get(week, 0.0)
        data['std_hatch_pct'].append(round(std_val, 2))

        data['weeks'].append(f"Week {week}")

        e_set = agg['egg_set'] or 1
        clear_p = (agg['clear_eggs'] / e_set) * 100
        rotten_p = (agg['rotten_eggs'] / e_set) * 100
        fertile_p = ((agg['egg_set'] - agg['clear_eggs'] - agg['rotten_eggs']) / e_set) * 100
        hatch_p = (agg['hatched_chicks'] / e_set) * 100

        avg_male = 0
        if agg['male_ratios']:
            avg_male = sum(agg['male_ratios']) / len(agg['male_ratios'])

        data['clear_pct'].append(round(clear_p, 2))
        data['rotten_pct'].append(round(rotten_p, 2))
        data['fertile_pct'].append(round(fertile_p, 2))
        data['hatch_pct'].append(round(hatch_p, 2))
        data['male_ratio_pct'].append(round(avg_male, 2))

        # Gather Notes & Medications for the specific week (Age based)
        # Week starts at: Intake + (Week-1)*7
        # Week ends at: Intake + Week*7 - 1
        if week == 0:
            start_date = flock.intake_date
            end_date = flock.intake_date
        elif week > 0:
            start_date = flock.intake_date + timedelta(days=((week - 1) * 7) + 1)
            end_date = flock.intake_date + timedelta(days=(week * 7))
        else:
            # Negative weeks (e.g. week -1 means days -7 to -1 before intake)
            start_date = flock.intake_date + timedelta(days=(week * 7))
            end_date = flock.intake_date + timedelta(days=((week + 1) * 7) - 1)

        logs = DailyLog.query.filter(
            DailyLog.flock_id == flock_id,
            DailyLog.date >= start_date,
            DailyLog.date <= end_date,
            DailyLog.clinical_notes != None,
            DailyLog.clinical_notes != ''
        ).all()

        meds = Medication.query.filter(
            Medication.flock_id == flock_id,
            Medication.start_date <= end_date,
            or_(Medication.end_date == None, Medication.end_date >= start_date)
        ).all()

        notes_parts = []
        if logs:
            notes_str = "; ".join([f"{l.date.strftime('%d/%m')}: {l.clinical_notes}" for l in logs])
            notes_parts.append(f"Notes: {notes_str}")

        if meds:
            meds_str = ", ".join([m.drug_name for m in meds]) # Just names to save space
            notes_parts.append(f"Meds: {meds_str}")

        data['notes'].append(" | ".join(notes_parts) if notes_parts else None)

    return render_template('hatchery_charts.html', flock=flock, data=data)

@app.route('/flock/<int:id>/hatchability/diagnosis/<date_str>', methods=['GET', 'POST'])
def hatchability_diagnosis(id, date_str):
    if current_user.dept not in FARM_HATCHERY_ADMIN_MGMT_DEPTS:
        return redirect(url_for('login'))

    is_readonly = request.args.get('readonly') == 'true'

    flock = Flock.query.get_or_404(id)
    try:
        setting_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format.', 'danger')
        return redirect(url_for('flock_hatchability', id=id))

    if request.method == 'POST':
        if current_user.dept == 'Farm' or is_readonly:
            flash("Read-only access.", "warning")
        else:
            h_id = request.form.get('hatchability_id')
            if h_id:
                h_record = Hatchability.query.get(h_id)
                if h_record and h_record.flock_id == id:
                    try:
                        h_record.clear_eggs = int(request.form.get('clear_eggs') or 0)
                        h_record.rotten_eggs = int(request.form.get('rotten_eggs') or 0)
                        h_record.hatched_chicks = int(request.form.get('hatched_chicks') or 0)
                        safe_commit()
                        flash('Hatchability record updated.', 'success')
                    except ValueError:
                        flash('Invalid input.', 'danger')
        return redirect(url_for('hatchability_diagnosis', id=id, date_str=date_str))

    records = Hatchability.query.filter_by(flock_id=id, setting_date=setting_date).all()
    if not records:
        flash('No hatchability records found for this date.', 'warning')
        return redirect(url_for('flock_hatchability', id=id))

    # Calculate Collection Window
    # Tue (1) -> Fri (4) to Mon (0) [Prev Fri, Sat, Sun, Mon]
    # Fri (4) -> Tue (1) to Thu (3) [Tue, Wed, Thu]
    weekday = setting_date.weekday() # Mon=0, Tue=1, ... Fri=4

    start_date = None
    end_date = None
    window_desc = ""

    if weekday == 1: # Tuesday
        # Window: Previous Friday (-4 days) to Monday (-1 day)
        start_date = setting_date - timedelta(days=4)
        end_date = setting_date - timedelta(days=1)
        window_desc = "Standard (Fri - Mon)"
    elif weekday == 4: # Friday
        # Window: Tuesday (-3 days) to Thursday (-1 day)
        start_date = setting_date - timedelta(days=3)
        end_date = setting_date - timedelta(days=1)
        window_desc = "Standard (Tue - Thu)"
    else:
        # Fallback: Just take previous 3 days
        start_date = setting_date - timedelta(days=3)
        end_date = setting_date - timedelta(days=1)
        window_desc = "Non-Standard Set Day (Assumed 3 days prior)"

    daily_logs = DailyLog.query.filter(
        DailyLog.flock_id == id,
        DailyLog.date >= start_date,
        DailyLog.date <= end_date
    ).order_by(DailyLog.date).all()

    # Active Medications
    # Meds active ANY time during the window
    # Med Start <= Window End AND (Med End is None OR Med End >= Window Start)
    medications = Medication.query.filter(
        Medication.flock_id == id,
        Medication.start_date <= end_date,
        or_(Medication.end_date == None, Medication.end_date >= start_date)
    ).all()

    # Aggregated Hatch Stats
    total_set = sum(r.egg_set for r in records)
    total_hatched = sum(r.hatched_chicks for r in records)
    total_clear = sum(r.clear_eggs for r in records)
    total_rotten = sum(r.rotten_eggs for r in records)

    avg_hatchability = (total_hatched / total_set * 100) if total_set > 0 else 0
    avg_clear = (total_clear / total_set * 100) if total_set > 0 else 0
    avg_rotten = (total_rotten / total_set * 100) if total_set > 0 else 0

    total_collected = 0
    total_hatching_eggs = 0
    for l in daily_logs:
        total_collected += (l.eggs_collected or 0)
        culls = (l.cull_eggs_jumbo or 0) + (l.cull_eggs_small or 0) + (l.cull_eggs_abnormal or 0) + (l.cull_eggs_crack or 0)
        total_hatching_eggs += ((l.eggs_collected or 0) - culls)

    return render_template('hatchability_diagnosis.html',
                           flock=flock,
                           setting_date=setting_date,
                           records=records,
                           daily_logs=daily_logs,
                           medications=medications,
                           window_start=start_date,
                           window_end=end_date,
                           window_desc=window_desc,
                           stats={
                               'set': total_set, 'hatched': total_hatched,
                               'hatch_pct': avg_hatchability,
                               'clear_pct': avg_clear, 'rotten_pct': avg_rotten,
                               'collected': total_collected,
                               'hatching_eggs': total_hatching_eggs,
                               'diff': total_hatching_eggs - total_set
                           },
                           readonly=is_readonly)


@app.route('/daily_log', methods=['GET', 'POST'])
@login_required
@dept_required('Farm')
def daily_log():
    if request.method == 'POST':
        house_id = request.form.get('house_id')
        date_str = request.form.get('date')
        
        flock = Flock.query.filter_by(house_id=house_id, status='Active').first()
        if not flock:
            if request.headers.get('Accept') == 'application/json':
                return jsonify({'success': False, 'error': 'No active flock found for this house.'}), 400
            flash('Error: No active flock found for this house.', 'danger')
            return redirect(url_for('daily_log'))
        
        try:
            log_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            if request.headers.get('Accept') == 'application/json':
                return jsonify({'success': False, 'error': 'Invalid date format.'}), 400
            flash('Error: Invalid date format.', 'danger')
            return redirect(url_for('daily_log'))
        
        # Gap Detection Logic
        from markupsafe import Markup
        if log_date > flock.intake_date:
            # We need to check all dates from intake_date to log_date - 1
            # We can find the missing dates by querying existing logs in that range
            existing_logs_dates = [
                d[0] for d in db.session.query(DailyLog.date).filter(
                    DailyLog.flock_id == flock.id,
                    DailyLog.date >= flock.intake_date,
                    DailyLog.date < log_date
                ).all()
            ]

            # Find the first missing date
            current_check_date = flock.intake_date
            missing_date = None
            while current_check_date < log_date:
                if current_check_date not in existing_logs_dates:
                    missing_date = current_check_date
                    break
                current_check_date += timedelta(days=1)

            if missing_date:
                missing_date_str = missing_date.strftime('%Y-%m-%d')
                missing_url = url_for('daily_log', house_id=house_id, date=missing_date_str)
                error_msg = f'Error: Data Gap Detected. Please <a href="{missing_url}" class="alert-link">complete the missing daily log for {missing_date_str}</a> before proceeding.'

                if request.headers.get('Accept') == 'application/json':
                    return jsonify({'success': False, 'error': error_msg}), 400

                flash(Markup(error_msg), 'danger')
                return redirect(url_for('daily_log', house_id=house_id, date=date_str))

        existing_log = DailyLog.query.filter_by(flock_id=flock.id, date=log_date).first()
        
        if existing_log:
            log = existing_log
            flash_msg = 'Daily Log updated successfully!'
        else:
            log = DailyLog(
                flock_id=flock.id,
                date=log_date,                body_weight_male=0,
                body_weight_female=0
            )
            db.session.add(log)
            flash_msg = 'Daily Log submitted successfully!'

        log.flock = flock
        db.session.add(log)

        try:
            update_log_from_request(log, request)
        except ValueError as e:
            db.session.rollback()
            if request.headers.get('Accept') == 'application/json':
                return jsonify({'success': False, 'error': str(e)}), 400
            flash(str(e), 'danger')
            return redirect(url_for('daily_log', house_id=house_id, date=date_str))

        # Automatic Production Trigger
        if log.eggs_collected > 0 and not flock.start_of_lay_date:
            flock.start_of_lay_date = log.date
            flash(f"First egg detected! Production tracking started for {flock.flock_id} from {log.date}.", "info")

        # Handle Vaccines (Mark as Completed)
        vaccine_present_ids = request.form.getlist('vaccine_present_ids')
        vaccine_completed_ids = request.form.getlist('vaccine_completed_ids')

        # Convert to integers for precise DB query
        int_vaccine_present_ids = []
        for vid in vaccine_present_ids:
            try:
                int_vaccine_present_ids.append(int(vid))
            except ValueError:
                pass

        if int_vaccine_present_ids:
            # Optimize N+1 Query: Bulk fetch instead of individual gets
            vaccines = Vaccine.query.filter(Vaccine.id.in_(int_vaccine_present_ids)).all()
            for vac in vaccines:
                if vac.flock_id == flock.id:
                    if str(vac.id) in vaccine_completed_ids:
                        vac.actual_date = log_date
                    elif vac.actual_date == log_date:
                        # Only unset if it was set to THIS date (don't clear history if logic changes)
                        vac.actual_date = None

        # Handle Multiple Medications
        med_names = request.form.getlist('med_drug_name[]')
        med_inventory_ids = request.form.getlist('med_inventory_id[]')
        med_dosages = request.form.getlist('med_dosage[]')
        med_amounts = request.form.getlist('med_amount_used[]') # Legacy text
        med_amount_qtys = request.form.getlist('med_amount_qty[]') # New numeric
        med_start_dates = request.form.getlist('med_start_date[]')
        med_end_dates = request.form.getlist('med_end_date[]')
        med_remarks = request.form.getlist('med_remarks[]')

        # Batch fetch inventory items
        unique_inv_ids = {int(iid) for iid in med_inventory_ids if iid and iid.isdigit()}
        inventory_items_dict = {}
        if unique_inv_ids:
            items = InventoryItem.query.filter(InventoryItem.id.in_(unique_inv_ids)).all()
            inventory_items_dict = {item.id: item for item in items}

        for i, name_val in enumerate(med_names):
            inv_id_val = med_inventory_ids[i] if i < len(med_inventory_ids) else None

            # Determine Name: Inventory Name > Manual Name
            item_name = name_val
            inv_id = None

            if inv_id_val and inv_id_val.isdigit():
                inv_id = int(inv_id_val)
                item = inventory_items_dict.get(inv_id)
                if item: item_name = item.name

            if not item_name and not inv_id:
                continue

            s_date = log_date
            s_date_val = med_start_dates[i] if i < len(med_start_dates) else None
            if s_date_val:
                try:
                    s_date = datetime.strptime(s_date_val, '%Y-%m-%d').date()
                except: pass

            e_date = None
            e_date_val = med_end_dates[i] if i < len(med_end_dates) else None
            if e_date_val:
                try:
                    e_date = datetime.strptime(e_date_val, '%Y-%m-%d').date()
                except: pass

            qty = None
            try:
                qty_val = med_amount_qtys[i] if i < len(med_amount_qtys) else None
                if qty_val: qty = float(qty_val)
            except: pass

            med = Medication(
                flock_id=flock.id,
                drug_name=item_name,
                inventory_item_id=inv_id,
                dosage=med_dosages[i] if i < len(med_dosages) else '',
                amount_used=med_amounts[i] if i < len(med_amounts) else '',
                amount_used_qty=qty,
                start_date=s_date,
                end_date=e_date,
                remarks=med_remarks[i] if i < len(med_remarks) else ''
            )
            db.session.add(med)

            # Auto-Deduct from Inventory
            if inv_id and qty and qty > 0:
                inv_item = inventory_items_dict.get(inv_id)
                if inv_item:
                    inv_item.current_stock -= qty
                    t = InventoryTransaction(
                        inventory_item_id=inv_id,
                        transaction_type='Usage',
                        quantity=qty,
                        transaction_date=s_date,
                        notes=f'Used in Daily Log: {flock.flock_id}'
                    )
                    db.session.add(t)

        try:
            safe_commit()
            recalculate_flock_inventory(flock.id)
            if request.headers.get('Accept') == 'application/json':
                house_status = check_daily_log_completion(flock.farm_id, log_date)
                return jsonify({
                    'success': True,
                    'message': flash_msg,
                    'houses': house_status,
                    'date': date_str
                })
            flash(flash_msg, 'success')
            return redirect(url_for('daily_log', house_id=house_id, date=date_str))
        except Exception as e:
            db.session.rollback()
            if request.headers.get('Accept') == 'application/json':
                return jsonify({'success': False, 'error': f"Database Error: {str(e)}"}), 500
            flash(f"Database Error: {str(e)}", 'danger')
            return redirect(url_for('daily_log', house_id=house_id, date=date_str))
        
    active_flocks = Flock.query.options(joinedload(Flock.house)).filter_by(status='Active').all()
    active_houses = [f.house for f in active_flocks]

    flock_phases = {}

    for f in active_flocks:
        flock_phases[f.house_id] = f.phase

    feed_codes = FeedCode.query.order_by(FeedCode.code.asc()).all()

    selected_house_id = request.args.get('house_id')
    selected_date_str = request.args.get('date')
    log = None
    vaccines_due = []

    # If log exists, we use log.flock.id. If not, we try selected_house_id.
    target_flock_id = None
    target_date = date.today()

    if selected_house_id and selected_date_str:
        try:
             h_id = int(selected_house_id)
             d_obj = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
             target_date = d_obj

             target_flock = Flock.query.filter_by(house_id=h_id, status='Active').first()
             if target_flock:
                 target_flock_id = target_flock.id
                 log = DailyLog.query.filter_by(flock_id=target_flock.id, date=d_obj).first()
        except:
             pass
    elif log:
        target_flock_id = log.flock_id
        target_date = log.date

    if target_flock_id:
        # Fetch relevant vaccines
        # Criteria: Actual Date is target_date OR (Actual is None AND Est Date <= target_date + 7)
        all_vacs = Vaccine.query.filter_by(flock_id=target_flock_id).all()
        lookahead = target_date + timedelta(days=7)

        for v in all_vacs:
            is_relevant = False
            if v.actual_date == target_date:
                is_relevant = True
            elif v.actual_date is None:
                if v.est_date and v.est_date <= lookahead:
                    is_relevant = True

            if is_relevant:
                vaccines_due.append(v)

        # Sort by est_date
        vaccines_due.sort(key=lambda x: x.est_date or date.max)

    # Fetch Inventory Items (Medications)
    medication_inventory = InventoryItem.query.filter_by(type='Medication').order_by(InventoryItem.name).all()

    return render_template('daily_log_form.html',
                           houses=active_houses,
                           flock_phases_json=json.dumps(flock_phases),
                           feed_codes=feed_codes,
                           log=log,
                           selected_house_id=int(selected_house_id) if selected_house_id and selected_house_id.isdigit() else None,
                           selected_date=selected_date_str,
                           vaccines_due=vaccines_due,
                           medication_inventory=medication_inventory)

@app.route('/api/daily_log/previous')
def get_previous_daily_log_data():
    house_id = request.args.get('house_id')
    date_str = request.args.get('date')

    if not house_id or not date_str:
        return jsonify({}), 400

    try:
        log_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({}), 400

    flock = Flock.query.filter_by(house_id=house_id, status='Active').first()
    if not flock:
        return jsonify({}), 404

    # Get previous log for pre-fill
    previous_log = DailyLog.query.filter(
        DailyLog.flock_id == flock.id,
        DailyLog.date < log_date
    ).order_by(DailyLog.date.desc()).first()

    # Get EXACT yesterday and day_minus_2 for validation
    from datetime import timedelta
    yesterday_log = DailyLog.query.filter_by(flock_id=flock.id, date=log_date - timedelta(days=1)).first()
    day_minus_2_log = DailyLog.query.filter_by(flock_id=flock.id, date=log_date - timedelta(days=2)).first()

    # Calculate current stock for live calculation
    # Sum mortality and culls up to the given date (exclusive)
    all_prev_logs = DailyLog.query.filter(
        DailyLog.flock_id == flock.id,
        DailyLog.date < log_date
    ).all()

    cum_mort_m = sum((l.mortality_male or 0) + (l.culls_male or 0) for l in all_prev_logs)
    cum_mort_f = sum((l.mortality_female or 0) + (l.culls_female or 0) for l in all_prev_logs)

    current_stock_m = (flock.intake_male or 0) - cum_mort_m
    current_stock_f = (flock.intake_female or 0) - cum_mort_f

    data = {
        'current_stock_m': current_stock_m,
        'current_stock_f': current_stock_f,
        'yesterday_feed_m': yesterday_log.feed_male_gp_bird if yesterday_log else 0,
        'yesterday_feed_f': yesterday_log.feed_female_gp_bird if yesterday_log else 0,
        'day_minus_2_feed_m': day_minus_2_log.feed_male_gp_bird if day_minus_2_log else 0,
        'day_minus_2_feed_f': day_minus_2_log.feed_female_gp_bird if day_minus_2_log else 0
    }

    if previous_log:
        data.update({
            'feed_program': previous_log.feed_program,
            'feed_code_male_id': previous_log.feed_code_male_id,
            'feed_code_female_id': previous_log.feed_code_female_id,
            'feed_male_gp_bird': previous_log.feed_male_gp_bird,
            'feed_female_gp_bird': previous_log.feed_female_gp_bird,
            'feed_cleanup_start': previous_log.feed_cleanup_start,
            'feed_cleanup_end': previous_log.feed_cleanup_end,
            'light_on_time': previous_log.light_on_time,
            'light_off_time': previous_log.light_off_time
        })

    return jsonify(data), 200

@app.route('/toggle_admin_view')
@login_required
def toggle_admin_view():
    if not current_user.role == 'Admin':
        flash("Unauthorized.", "danger")
        return redirect(url_for('index'))

    session['hide_admin_view'] = not session.get('hide_admin_view', False)
    return redirect(request.referrer or url_for('index'))

@app.context_processor
def utility_processor():
    # Inject Effective Admin & Dept for Simulation
    real_is_admin = getattr(current_user, 'role', None) == 'Admin'
    hide_view = session.get('hide_admin_view', False)

    effective_is_admin = real_is_admin
    effective_dept = getattr(current_user, "dept", None)
    effective_role = getattr(current_user, "role", None)

    if real_is_admin and hide_view:
        effective_is_admin = False
        # Infer Dept/Role based on Context
        path = request.path
        if path.startswith('/executive'):
             effective_dept = 'Management'
             effective_role = 'Management'
        elif path.startswith('/hatchery') or 'hatchability' in path or 'hatch' in path:
             # 'hatch' covers hatchery_dashboard, hatchery_charts, import_hatchability, etc.
             effective_dept = 'Hatchery'
             effective_role = 'Worker'
        else:
             effective_dept = 'Farm'
             effective_role = 'Worker'

    def get_partition_val(log, name, type_):
        if not log: return 0.0
        for pw in log.partition_weights:
            if pw.partition_name == name:
                return pw.body_weight if type_ == 'bw' else pw.uniformity
        return 0.0

    def get_ui_elements(section):
        # Admin sees everything (sorted)
        # Standard users see only visible
        query = UIElement.query.filter_by(section=section).order_by(UIElement.order_index.asc())
        if not effective_is_admin:
            query = query.filter_by(is_visible=True)
        return query.all()

    from flask import g
    class AnonymousUser:
        is_authenticated = False
        username = ''
        role = ''

    return dict(get_partition_val=get_partition_val,
                get_ui_elements=get_ui_elements,
                is_admin=effective_is_admin,
                real_is_admin=real_is_admin,
                user_dept=effective_dept,
                user_role=effective_role,
                is_debug=app.debug,
                current_user=current_user if hasattr(g, 'user') and current_user else AnonymousUser())

@app.route('/admin/ui', methods=['GET', 'POST'])
@login_required
def admin_ui_update():
    if not current_user.role == 'Admin':
        return redirect(url_for('index'))

    if request.method == 'POST':
        # Process updates
        # Form data: id[], order_{id}, label_{id}, visible_{id}
        ids = request.form.getlist('id[]')

        int_ids = [int(id_str) for id_str in ids if id_str.isdigit()]
        ui_elements = UIElement.query.filter(UIElement.id.in_(int_ids)).all()
        ui_element_dict = {elem.id: elem for elem in ui_elements}

        for id_str in ids:
            eid = int(id_str) if id_str.isdigit() else 0
            elem = ui_element_dict.get(eid)
            if not elem: continue

            # Update Label
            label = request.form.get(f'label_{eid}')
            if label: elem.label = label

            # Update Order
            order = request.form.get(f'order_{eid}')
            if order and order.isdigit():
                elem.order_index = int(order)

            # Update Visibility
            # Checkboxes only send value if checked.
            is_vis = request.form.get(f'visible_{eid}')
            elem.is_visible = (is_vis is not None)

        safe_commit()
        flash('UI configuration updated.', 'success')
        return redirect(url_for('admin_ui_update'))

    # GET: Fetch all elements grouped by section
    elements = {}
    all_elems = UIElement.query.order_by(UIElement.order_index.asc()).all()
    for e in all_elems:
        if e.section not in elements:
            elements[e.section] = []
        elements[e.section].append(e)

    return render_template('admin/ui_manager.html', elements=elements)

@app.route('/admin/control-panel')
@login_required
def admin_control_panel():
    if not current_user.role == 'Admin':
        flash("Access Denied: Admin only.", "danger")
        return redirect(url_for('index'))

    gs = GlobalStandard.query.first()
    login_required = gs.login_required if gs and hasattr(gs, 'login_required') else True

    return render_template('admin/control_panel.html', login_required=login_required)

@app.route('/change_theme', methods=['POST'])
def change_theme():
    if not current_user.id:
        flash("You must be logged in to change your theme.", "warning")
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if user:
        theme = request.form.get('theme', 'base_tabler.html')
        # Validate theme input to avoid arbitrary file injection
        valid_themes = [
            'base_tabler.html', 'base_argon.html', 'base_volt.html',
            'base_horizon.html', 'base_material.html', 'base_soft.html',
            'base_lightblue.html', 'base_bw.html'
        ]
        if theme in valid_themes:
            user.theme = theme
            safe_commit()
            flash("Theme successfully updated.", "success")
        else:
            flash("Invalid theme selected.", "danger")

    return redirect(request.referrer or url_for('index'))

@app.route('/admin/toggle_login', methods=['POST'])
@login_required
def toggle_login():
    if not current_user.role == 'Admin':
        return redirect(url_for('index'))

    gs = GlobalStandard.query.first()
    if not gs:
        gs = GlobalStandard()
        db.session.add(gs)

    # Toggle
    current = gs.login_required if hasattr(gs, 'login_required') else True
    gs.login_required = not current
    safe_commit()

    status = "ON" if gs.login_required else "OFF"

    if gs.login_required:
        session.clear()
        flash("Login Page enabled. Please log in.", "info")
        return redirect(url_for('login'))
    else:
        flash(f"Login Page turned {status}.", "warning")

    return redirect(url_for('admin_control_panel'))

@app.route('/admin/performance_report')
@login_required
def admin_performance_report():
    if not current_user.role == 'Admin':
        return redirect(url_for('index'))

    return render_template('admin/performance_report.html')

@app.route('/admin/houses')
@login_required
def admin_houses():
    if not current_user.role == 'Admin':
        flash("Access Denied: Admin only.", "danger")
        return redirect(url_for('index'))

    houses = House.query.order_by(House.name).all()
    # Check if houses can be deleted (no flocks)
    for h in houses:
        h.can_delete = (Flock.query.filter_by(house_id=h.id).count() == 0)

    return render_template('admin/houses.html', houses=houses)

@app.route('/admin/houses/add', methods=['POST'])
@login_required
def admin_house_add():
    if not current_user.role == 'Admin': return redirect(url_for('index'))

    name = request.form.get('name').strip()
    if not name:
        flash("House name is required.", "danger")
    elif House.query.filter_by(name=name).first():
        flash(f"House '{name}' already exists.", "warning")
    else:
        db.session.add(House(name=name))
        safe_commit()
        flash(f"House '{name}' added.", "success")

    return redirect(url_for('admin_houses'))

@app.route('/admin/houses/edit/<int:id>', methods=['POST'])
@login_required
def admin_house_edit(id):
    if not current_user.role == 'Admin': return redirect(url_for('index'))

    house = House.query.get_or_404(id)
    new_name = request.form.get('name').strip()

    if not new_name:
        flash("New name is required.", "danger")
    elif new_name != house.name and House.query.filter_by(name=new_name).first():
        flash(f"House '{new_name}' already exists.", "warning")
    else:
        old_name = house.name
        house.name = new_name
        safe_commit()
        flash(f"Renamed House '{old_name}' to '{new_name}'.", "success")

    return redirect(url_for('admin_houses'))

@app.route('/admin/houses/delete/<int:id>', methods=['POST'])
@login_required
def admin_house_delete(id):
    if not current_user.role == 'Admin': return redirect(url_for('index'))

    house = House.query.get_or_404(id)
    if Flock.query.filter_by(house_id=id).count() > 0:
        flash(f"Cannot delete House '{house.name}' because it has flocks associated with it.", "danger")
    else:
        db.session.delete(house)
        safe_commit()
        flash(f"House '{house.name}' deleted.", "info")

    return redirect(url_for('admin_houses'))

@app.route('/daily_log/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@dept_required('Farm')
def edit_daily_log(id):
    log = DailyLog.query.get_or_404(id)
    
    if request.method == 'POST':
        # Handle Vaccines
        vaccine_present_ids = request.form.getlist('vaccine_present_ids')
        vaccine_completed_ids = request.form.getlist('vaccine_completed_ids')

        # Convert to integers for precise DB query
        int_vaccine_present_ids = []
        for vid in vaccine_present_ids:
            try:
                int_vaccine_present_ids.append(int(vid))
            except ValueError:
                pass

        if int_vaccine_present_ids:
            # Optimize N+1 Query: Bulk fetch instead of individual gets
            vaccines = Vaccine.query.filter(Vaccine.id.in_(int_vaccine_present_ids)).all()
            for vac in vaccines:
                if vac.flock_id == log.flock_id:
                    if str(vac.id) in vaccine_completed_ids:
                        vac.actual_date = log.date
                    elif vac.actual_date == log.date:
                        vac.actual_date = None

        # Handle Multiple Medications
        med_names = request.form.getlist('med_drug_name[]')
        med_inventory_ids = request.form.getlist('med_inventory_id[]')
        med_dosages = request.form.getlist('med_dosage[]')
        med_amounts = request.form.getlist('med_amount_used[]')
        med_amount_qtys = request.form.getlist('med_amount_qty[]')
        med_start_dates = request.form.getlist('med_start_date[]')
        med_end_dates = request.form.getlist('med_end_date[]')
        med_remarks = request.form.getlist('med_remarks[]')

        # Batch fetch inventory items
        unique_inv_ids = {int(iid) for iid in med_inventory_ids if iid and iid.isdigit()}
        inventory_items_dict = {}
        if unique_inv_ids:
            items = InventoryItem.query.filter(InventoryItem.id.in_(unique_inv_ids)).all()
            inventory_items_dict = {item.id: item for item in items}

        for i, name_val in enumerate(med_names):
            inv_id_val = med_inventory_ids[i] if i < len(med_inventory_ids) else None

            item_name = name_val
            inv_id = None
            if inv_id_val and inv_id_val.isdigit():
                inv_id = int(inv_id_val)
                item = inventory_items_dict.get(inv_id)
                if item: item_name = item.name

            if not item_name and not inv_id:
                continue

            s_date = log.date
            s_date_val = med_start_dates[i] if i < len(med_start_dates) else None
            if s_date_val:
                try:
                    s_date = datetime.strptime(s_date_val, '%Y-%m-%d').date()
                except: pass

            e_date = None
            e_date_val = med_end_dates[i] if i < len(med_end_dates) else None
            if e_date_val:
                try:
                    e_date = datetime.strptime(e_date_val, '%Y-%m-%d').date()
                except: pass

            qty = None
            try:
                qty_val = med_amount_qtys[i] if i < len(med_amount_qtys) else None
                if qty_val: qty = float(qty_val)
            except: pass

            med = Medication(
                flock_id=log.flock_id,
                drug_name=item_name,
                inventory_item_id=inv_id,
                dosage=med_dosages[i] if i < len(med_dosages) else '',
                amount_used=med_amounts[i] if i < len(med_amounts) else '',
                amount_used_qty=qty,
                start_date=s_date,
                end_date=e_date,
                remarks=med_remarks[i] if i < len(med_remarks) else ''
            )
            db.session.add(med)

            if inv_id and qty and qty > 0:
                inv_item = inventory_items_dict.get(inv_id)
                if inv_item:
                    inv_item.current_stock -= qty
                    t = InventoryTransaction(
                        inventory_item_id=inv_id,
                        transaction_type='Usage',
                        quantity=qty,
                        transaction_date=s_date,
                        notes=f'Used in Daily Log: {log.flock.flock_id}'
                    )
                    db.session.add(t)

        try:
            update_log_from_request(log, request)
        except ValueError as e:
            db.session.rollback()
            if request.headers.get('Accept') == 'application/json':
                return jsonify({'success': False, 'error': str(e)}), 400
            flash(str(e), 'danger')
            return redirect(url_for('edit_daily_log', id=id))

        # Automatic Production Trigger
        if log.eggs_collected > 0 and not log.flock.start_of_lay_date:
            log.flock.start_of_lay_date = log.date
            flash(f"First egg detected! Production tracking started for {log.flock.flock_id} from {log.date}.", "info")

        try:
            safe_commit()
            recalculate_flock_inventory(log.flock_id)
            if request.headers.get('Accept') == 'application/json':
                house_status = check_daily_log_completion(log.flock.farm_id, log.date)
                return jsonify({
                    'success': True,
                    'message': 'Log updated successfully.',
                    'houses': house_status,
                    'date': log.date.strftime('%Y-%m-%d')
                })
            flash('Log updated successfully.', 'success')
            return redirect(url_for('edit_daily_log', id=id))
        except Exception as e:
            db.session.rollback()
            if request.headers.get('Accept') == 'application/json':
                return jsonify({'success': False, 'error': f"Database Error: {str(e)}"}), 500
            flash(f"Database Error: {str(e)}", 'danger')
            return redirect(url_for('edit_daily_log', id=id))
    
    feed_codes = FeedCode.query.order_by(FeedCode.code.asc()).all()

    vaccines_due = []
    target_flock_id = log.flock_id
    target_date = log.date

    all_vacs = Vaccine.query.filter_by(flock_id=target_flock_id).all()
    lookahead = target_date + timedelta(days=7)

    for v in all_vacs:
        is_relevant = False
        if v.actual_date == target_date:
            is_relevant = True
        elif v.actual_date is None:
            if v.est_date and v.est_date <= lookahead:
                is_relevant = True

        if is_relevant:
            vaccines_due.append(v)

    vaccines_due.sort(key=lambda x: x.est_date or date.max)

    medication_inventory = InventoryItem.query.filter_by(type='Medication').order_by(InventoryItem.name).all()

    return render_template('daily_log_form.html', log=log, houses=[log.flock.house], feed_codes=feed_codes, vaccines_due=vaccines_due, medication_inventory=medication_inventory)

@app.route('/import', methods=['GET', 'POST'])
@login_required
@dept_required('Farm')
def import_data():
    if request.method == 'POST':
        # Check for Confirmation
        confirm_files = request.form.getlist('confirm_files')
        if confirm_files:
            results = []
            errors = []

            for confirm_filename in confirm_files:
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'temp', confirm_filename)
                if not os.path.exists(filepath):
                    errors.append(f"{confirm_filename}: File not found.")
                    continue

                try:
                    process_import(filepath, commit=True, preview=False)
                    os.remove(filepath)
                    results.append(confirm_filename)
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    errors.append(f"{confirm_filename}: {str(e)}")

            if results:
                flash(f"Successfully imported {len(results)} files.", 'success')
            if errors:
                for err in errors:
                    flash(f"Error: {err}", 'danger')

            return redirect(url_for('index'))

        if 'files' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        
        files = request.files.getlist('files')
        if not files or files[0].filename == '':
            flash('No selected files', 'danger')
            return redirect(request.url)

        all_changes = []
        all_warnings = []
        temp_filenames = []

        for file in files:
            if file and file.filename.endswith('.xlsx'):
                try:
                    # Save to temp
                    safe_name = secure_filename(f"{int(time.time())}_{file.filename}")
                    temp_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'temp')
                    os.makedirs(temp_dir, exist_ok=True)
                    filepath = os.path.join(temp_dir, safe_name)
                    file.save(filepath)
                    temp_filenames.append(safe_name)

                    changes, warnings = process_import(filepath, commit=False, preview=True)

                    # Add source filename to changes
                    for c in changes:
                        c['source_file'] = file.filename

                    all_changes.extend(changes)

                    # Prefix warnings with filename
                    for w in warnings:
                        all_warnings.append(f"[{file.filename}] {w}")

                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    flash(f"{file.filename}: {str(e)}", 'danger')
                    return redirect(request.url)
            else:
                if file.filename:
                    flash(f"{file.filename}: Invalid type (must be .xlsx)", 'danger')
                    return redirect(request.url)

        if all_changes:
            return render_template('import_preview.html', changes=all_changes, warnings=all_warnings, filenames=temp_filenames)

        flash("No valid data found to import.", "warning")
        return redirect(url_for('index'))
            
    return render_template('import.html')

@app.route('/import_hatchability', methods=['POST'])
@login_required
@dept_required('Hatchery')
def import_hatchability():
    if 'file' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('import_data'))

    file = request.files['file']
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('import_data'))

    if file and file.filename.endswith('.xlsx'):
        try:
            created, updated = process_hatchability_import(file)
            flash(f'Hatchability data imported successfully. Created: {created}, Updated: {updated}', 'success')
        except Exception as e:
            import traceback
            traceback.print_exc()
            flash(f'Error importing hatchability: {str(e)}', 'danger')
    else:
        flash('Invalid file type. Please upload an Excel file (.xlsx).', 'danger')

    return redirect(url_for('import_data'))

def seed_arbor_acres_standards():
    filepath = os.path.join(basedir, 'Arbor_Acres_Plus_S_Complete_Production_Standards.xlsx')
    if not os.path.exists(filepath):
        return False, "File 'Arbor_Acres_Plus_S_Complete_Production_Standards.xlsx' not found."

    try:
        df = pd.read_excel(filepath)

        # Columns: 'Production Week', 'Age (Days)', 'Age (Weeks)', 'Std Egg Prod %', 'Std Egg Wt (g)', 'Std Hatch %', 'Std Cum Eggs HHA', 'Std Cum Hatching HHA', 'Std Cum Chicks HHA'

        # Filter: Age (Weeks) >= 25
        # Assuming Age (Weeks) is column 'Age (Weeks)'
        if 'Age (Weeks)' not in df.columns:
            return False, "Column 'Age (Weeks)' not found."

        df_filtered = df[df['Age (Weeks)'] >= 25]

        # Pre-fetch all existing standards into a dictionary keyed by week
        existing_standards = {s.week: s for s in Standard.query.all()}

        count = 0
        for index, row in df_filtered.iterrows():
            week = int(row['Age (Weeks)'])
            prod_week = int(row['Production Week']) if pd.notna(row['Production Week']) else None

            std_egg_prod = float(row['Std Egg Prod %']) if pd.notna(row['Std Egg Prod %']) else 0.0
            std_egg_wt = float(row['Std Egg Wt (g)']) if pd.notna(row['Std Egg Wt (g)']) else 0.0
            std_hatch = float(row['Std Hatch %']) if pd.notna(row['Std Hatch %']) else 0.0
            std_cum_eggs_hha = float(row['Std Cum Eggs HHA']) if pd.notna(row['Std Cum Eggs HHA']) else 0.0
            std_cum_hatching_hha = float(row['Std Cum Hatching HHA']) if pd.notna(row['Std Cum Hatching HHA']) else 0.0
            std_cum_chicks_hha = float(row['Std Cum Chicks HHA']) if pd.notna(row['Std Cum Chicks HHA']) else 0.0
            std_hatch_egg_pct = float(row['Std Hatching Egg %']) if 'Std Hatching Egg %' in row and pd.notna(row['Std Hatching Egg %']) else 0.0

            # Find or Create Standard
            s = existing_standards.get(week)
            if not s:
                s = Standard(week=week)
                db.session.add(s)
                existing_standards[week] = s

            # Update Fields
            s.production_week = prod_week
            s.std_egg_prod = std_egg_prod
            s.std_egg_weight = std_egg_wt
            s.std_hatchability = std_hatch
            s.std_cum_eggs_hha = std_cum_eggs_hha
            s.std_cum_hatching_eggs_hha = std_cum_hatching_hha
            s.std_cum_chicks_hha = std_cum_chicks_hha
            s.std_hatching_egg_pct = std_hatch_egg_pct

            count += 1

        safe_commit()
        return True, f"Imported/Updated {count} weeks of Arbor Acres standards."

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, f"Error importing Arbor Acres standards: {str(e)}"

def seed_standards_from_file():
    filepath = os.path.join(basedir, 'SLH Daily Aviagen.xlsx')
    if not os.path.exists(filepath):
        return False, "File 'SLH Daily Aviagen.xlsx' not found."

    try:
        # Standard BW starts at row 507 (0-indexed 506? No, process_import uses skiprows=507 so row 508 is index 0?)
        # Let's align with process_import logic: skiprows=507 means row 508 is index 0.
        # But previous inspection showed valid data there.

        df = pd.read_excel(filepath, sheet_name='TEMPLATE', header=None, skiprows=507, nrows=70)

        # Columns based on inspection:
        # 0: Week
        # 14: Standard Mortality % (e.g. 0.003 for 0.3%)
        # 32: Std Male BW
        # 33: Std Female BW
        # 19: Egg Prod % (Empty in file but mapped)
        # 27: Egg Weight (Empty)
        # 26: Hatchability (Empty)

        # Pre-fetch existing standards to avoid N+1 queries
        existing_standards = {s.week: s for s in Standard.query.all()}

        count = 0
        for index, row in df.iterrows():
            try:
                week_val = int(row[0])
            except (ValueError, TypeError):
                continue

            std_mort = float(row[14]) * 100 if pd.notna(row[14]) else 0.0 # Convert 0.003 to 0.3 if needed?
            # Wait, inspection showed 0.003. Usually displayed as %. 0.3% is reasonable daily? Or weekly?
            # Header says "STANDARD MORTALITY%". 0.003 is 0.3%.
            # app.py uses float. Let's store as percentage value (0.3).

            std_bw_m = int(row[32]) if pd.notna(row[32]) else 0
            std_bw_f = int(row[33]) if pd.notna(row[33]) else 0

            # Missing Data placeholders
            # Col 19: Egg Prod % (0.83 = 83%)
            std_egg_prod = float(row[19]) * 100 if pd.notna(row[19]) else 0.0

            # Col 27: Egg Weight (g)
            std_egg_weight = float(row[27]) if pd.notna(row[27]) else 0.0

            # Col 26 is H.E% (Hatching Egg %), NOT Hatchability.
            # We do not map it to std_hatchability unless we add std_hatching_egg_pct to Standard model.
            std_hatch = 0.0

            # Check existing
            s = existing_standards.get(week_val)
            if not s:
                s = Standard(week=week_val)
                db.session.add(s)
                existing_standards[week_val] = s

            s.std_mortality_male = std_mort # Using same for both sexes if only one col
            s.std_mortality_female = std_mort
            s.std_bw_male = std_bw_m
            s.std_bw_female = std_bw_f
            s.std_egg_prod = std_egg_prod
            s.std_egg_weight = std_egg_weight
            s.std_hatchability = std_hatch

            count += 1

        safe_commit()
        return True, f"Seeded/Updated {count} weeks of standards."

    except Exception as e:
        return False, f"Error seeding standards: {str(e)}"

def process_hatchability_import(file):
    import pandas as pd
    xls = pd.ExcelFile(file)
    # Assume data is in the "Data" sheet or the first sheet if "Data" not found
    sheet_name = "Data" if "Data" in xls.sheet_names else xls.sheet_names[0]

    # Read header first to determine structure
    df = pd.read_excel(xls, sheet_name=sheet_name)

    # Required headers logic from template
    # Template: A=Setting, B=Candling, C=Hatching, D=FlockID, E=EggSet, F=Clear, G=%, H=Rotten, I=%, J=Hatchable, K=%, L=TotalHatched, M=%, N=MaleRatio

    # We will iterate row by row.
    # Check for empty df
    if df.empty:
        return 0, 0

    # Check columns
    # If headers are 'Setting Date', 'Flock ID' etc.

    col_map = {}

    def normalize(s):
        return str(s).strip().lower().replace(' ', '_')

    for i, col in enumerate(df.columns):
        norm = normalize(col)

        # Check for explicit percentage/ratio to EXCLUDE from count fields
        is_pct = '%' in norm or norm.endswith('_p') or norm.endswith('_pct') or 'ratio' in norm or 'percentage' in norm

        if 'setting' in norm and 'date' in norm: col_map['setting_date'] = i
        elif 'candling' in norm and 'date' in norm: col_map['candling_date'] = i
        elif 'hatching' in norm and 'date' in norm: col_map['hatching_date'] = i
        elif 'flock' in norm: col_map['flock_id'] = i
        elif 'egg' in norm and 'set' in norm: col_map['egg_set'] = i

        # Prefer FIRST match for counts (to handle duplicate 'Rotten Egg' headers where first is count)
        # And strictly exclude percentage-like columns
        elif 'clear' in norm and not is_pct:
            if 'clear_eggs' not in col_map: col_map['clear_eggs'] = i

        elif 'rotten' in norm and not is_pct:
            if 'rotten_eggs' not in col_map: col_map['rotten_eggs'] = i

        elif 'hatched' in norm and ('total' in norm or 'chicks' in norm): col_map['hatched_chicks'] = i
        elif 'male' in norm and 'ratio' in norm: col_map['male_ratio'] = i

    # Fallback to fixed indices if not found (Template standard)
    if 'setting_date' not in col_map: col_map['setting_date'] = 0
    if 'candling_date' not in col_map: col_map['candling_date'] = 1
    if 'hatching_date' not in col_map: col_map['hatching_date'] = 2
    if 'flock_id' not in col_map: col_map['flock_id'] = 3
    if 'egg_set' not in col_map: col_map['egg_set'] = 4
    if 'clear_eggs' not in col_map: col_map['clear_eggs'] = 5
    if 'rotten_eggs' not in col_map: col_map['rotten_eggs'] = 7 # H
    if 'hatched_chicks' not in col_map: col_map['hatched_chicks'] = 11 # L
    if 'male_ratio' not in col_map: col_map['male_ratio'] = 13 # N

    def get_val(row, key, transform=None):
        idx = col_map.get(key)
        if idx is not None and idx < len(row):
            val = row.iloc[idx]
            if pd.isna(val): return None # Explicitly None for Blanks/NaN

            # Check for Empty String or Whitespace
            if isinstance(val, str) and not val.strip():
                return None

            if transform:
                try: return transform(val)
                except: return None
            return val
        return None

    def parse_date(d):
        if hasattr(d, 'date'): return d.date()
        if isinstance(d, str):
            for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                try: return datetime.strptime(d, fmt).date()
                except: continue
        return None

    # Pre-fetch data for matching
    all_houses = House.query.all()
    house_map = {h.name: h.id for h in all_houses} # Name -> ID

    # Fetch all flocks, organize by house
    all_flocks = Flock.query.options(joinedload(Flock.house)).order_by(Flock.intake_date.desc()).all()
    flocks_by_house = {} # house_id -> list of Flock objects sorted desc
    for f in all_flocks:
        if f.house_id not in flocks_by_house:
            flocks_by_house[f.house_id] = []
        flocks_by_house[f.house_id].append(f)

    # Caches for performance optimization (N+1 query resolution)
    logs_cache = {} # flock_id -> list of DailyLog
    hatch_cache = {} # flock_id -> list of Hatchability (sorted by setting_date)

    created_count = 0
    updated_count = 0

    for index, row in df.iterrows():
        # Validations
        s_date = get_val(row, 'setting_date', parse_date)
        f_name_input = get_val(row, 'flock_id', str)

        if not s_date or not f_name_input:
            continue

        f_name = f_name_input.strip()

        # 1. Match House
        house_id = house_map.get(f_name)
        if not house_id:
            # Skip if House not found (as per requirement)
            continue

        # 2. Match Flock in House by Date
        # Find first flock where intake_date <= s_date
        target_flock = None
        target_flock_id = None
        candidates = flocks_by_house.get(house_id, [])

        for f in candidates:
            if f.intake_date <= s_date:
                target_flock = f
                target_flock_id = f.id
                break

        if not target_flock_id:
            # No valid flock found for this date
            continue

        # Populate caches for this flock if needed
        if target_flock_id not in logs_cache:
            logs_cache[target_flock_id] = DailyLog.query.filter_by(flock_id=target_flock_id).order_by(DailyLog.date).all()
        if target_flock_id not in hatch_cache:
            hatch_cache[target_flock_id] = Hatchability.query.filter_by(flock_id=target_flock_id).order_by(Hatchability.setting_date).all()

        # Extract values (None if blank)
        c_date = get_val(row, 'candling_date', parse_date)
        h_date = get_val(row, 'hatching_date', parse_date)
        e_set = get_val(row, 'egg_set', int)
        c_eggs = get_val(row, 'clear_eggs', int)
        r_eggs = get_val(row, 'rotten_eggs', int)
        h_chicks = get_val(row, 'hatched_chicks', int)

        # Determine last_hatch_date from cache for male ratio calculation
        last_hatch_date = None
        for h_rec in reversed(hatch_cache[target_flock_id]):
            if h_rec.setting_date < s_date:
                last_hatch_date = h_rec.setting_date
                break

        # Always fetch Male Ratio from Farm Database (using optimized call)
        m_ratio, _ = calculate_male_ratio(target_flock_id, s_date,
                                          flock_obj=target_flock,
                                          logs=logs_cache[target_flock_id],
                                          last_hatch_date=last_hatch_date,
                                          hatchery_records=hatch_cache[target_flock_id])

        # Check existing record in cache
        existing = next((h_rec for h_rec in hatch_cache[target_flock_id] if h_rec.setting_date == s_date), None)
        if existing:
            # Smart Patch Update
            updated_fields = []

            # Helper to update only if not None
            def update_if_present(obj, attr, val, field_name):
                if val is not None:
                    old_val = getattr(obj, attr)
                    if old_val != val:
                        setattr(obj, attr, val)
                        updated_fields.append(field_name)

            update_if_present(existing, 'candling_date', c_date, 'Candling Date')
            update_if_present(existing, 'hatching_date', h_date, 'Hatching Date')
            update_if_present(existing, 'egg_set', e_set, 'Egg Set')
            update_if_present(existing, 'clear_eggs', c_eggs, 'Clear Eggs')
            update_if_present(existing, 'rotten_eggs', r_eggs, 'Rotten Eggs')
            update_if_present(existing, 'hatched_chicks', h_chicks, 'Hatched Chicks')

            # Implicit update of Male Ratio
            if existing.male_ratio_pct != m_ratio:
                 existing.male_ratio_pct = m_ratio

            if updated_fields:
                updated_count += 1
                # Audit Log (Console for now)
                print(f"[AUDIT] Hatchery Record updated via Excel Import (Fields: {', '.join(updated_fields)}) for Flock {target_flock_id} on {s_date}")

        else:
            # Insert Record
            # Default dates if missing
            final_c_date = c_date or (s_date + timedelta(days=18))
            final_h_date = h_date or (s_date + timedelta(days=21))

            h = Hatchability(
                flock_id=target_flock_id,
                setting_date=s_date,
                candling_date=final_c_date,
                hatching_date=final_h_date,
                egg_set=e_set or 0,
                clear_eggs=c_eggs or 0,
                rotten_eggs=r_eggs or 0,
                hatched_chicks=h_chicks or 0,
                male_ratio_pct=m_ratio
            )
            db.session.add(h)
            hatch_cache[target_flock_id].append(h)
            hatch_cache[target_flock_id].sort(key=lambda x: x.setting_date)
            created_count += 1

    safe_commit()
    return created_count, updated_count

def process_import(file, commit=True, preview=False):
    xls = pd.ExcelFile(file)
    sheets = xls.sheet_names
    
    ignore_sheets = ['DASHBOARD', 'CHART', 'SUMMARY', 'TEMPLATE']

    all_houses_map = {h.name: h.id for h in House.query.all()}

    flock_query = db.session.query(Flock.id, Flock.house_id, Flock.intake_date).all()
    all_flocks_map = {}
    flock_counts = {}

    for f_id, f_house_id, f_intake_date in flock_query:
        if f_intake_date:
             all_flocks_map[(f_house_id, f_intake_date)] = f_id
        flock_counts[f_house_id] = flock_counts.get(f_house_id, 0) + 1
    
    changes = []
    all_warnings = []

    for sheet_name in sheets:
        if sheet_name.upper() in ignore_sheets:
            continue
            
        # Optimization: Read the full sheet once
        df_full = pd.read_excel(xls, sheet_name=sheet_name, header=None)

        # 1. Metadata (First 10 rows)
        df_meta = df_full.iloc[:10].copy() if df_full.shape[0] > 0 else pd.DataFrame()
        
        def get_val(r, c):
            try:
                val = df_meta.iloc[r, c]
                return val if pd.notna(val) else None
            except IndexError:
                return None

        def parse_date(date_val):
            if pd.isna(date_val):
                return None
            if hasattr(date_val, 'date'):
                return date_val.date()
            if isinstance(date_val, str):
                formats = ['%Y-%m-%d', '%d/%m/%y', '%d/%m/%Y', '%m/%d/%Y', '%m/%d/%Y']
                for fmt in formats:
                    try:
                        return datetime.strptime(date_val, fmt).date()
                    except ValueError:
                        continue
            return None

        house_name_cell = str(get_val(1, 1)).strip()
        house_name = house_name_cell if house_name_cell and house_name_cell != 'nan' else sheet_name
        
        def safe_int(val):
            try: return int(float(val)) if val is not None else 0
            except: return 0

        intake_female = safe_int(get_val(2, 1))
        intake_male = safe_int(get_val(3, 1))
        intake_date_val = get_val(4, 1)
        
        if not intake_date_val:
            print(f"Skipping sheet {sheet_name}: No Intake Date found.")
            continue
            
        house_id = all_houses_map.get(house_name)
        if not house_id:
            house = House(name=house_name)
            db.session.add(house)
            db.session.flush()
            house_id = house.id
            all_houses_map[house_name] = house_id
            if commit:
                safe_commit()
        
        intake_date = parse_date(intake_date_val)
        if not intake_date:
            print(f"Skipping sheet {sheet_name}: Invalid Date {intake_date_val}")
            continue
            
        date_str = intake_date.strftime('%y%m%d')
        
        flock_id = all_flocks_map.get((house_id, intake_date))
        if not flock_id:
            current_count = flock_counts.get(house_id, 0)
            n = current_count + 1
            flock_uid_str = f"{house_name}_{date_str}_Batch{n}"
            
            flock = Flock(
                house_id=house_id,
                flock_id=flock_uid_str,
                intake_date=intake_date,
                intake_male=intake_male,
                intake_female=intake_female,
                status='Active'
            )
            db.session.add(flock)
            db.session.flush()
            flock_id = flock.id
            all_flocks_map[(house_id, intake_date)] = flock_id
            flock_counts[house_id] = n
            if commit:
                safe_commit()
            
            initialize_sampling_schedule(flock_id, commit=commit)
            initialize_vaccine_schedule(flock_id, commit=commit)

        existing_logs_dict = {log.date: log for log in DailyLog.query.filter_by(flock_id=flock_id).all()}

        # 2. Standards (Row 507+, 70 rows)
        if df_full.shape[0] > 507:
            df_std = df_full.iloc[507:507+70].copy()
        else:
            df_std = pd.DataFrame()

        standard_bw_map = {}
        missing_std_weeks = []

        if df_std.shape[1] > 33:
            weeks = df_std.iloc[:, 0]
            males = df_std.iloc[:, 32]
            females = df_std.iloc[:, 33]

            for w, m, f in zip(weeks, males, females):
                try:
                    week_val = int(w)
                    m_val = float(m) if pd.notna(m) else 0.0
                    f_val = float(f) if pd.notna(f) else 0.0
                    standard_bw_map[week_val] = (m_val, f_val)
                except (ValueError, TypeError):
                    if pd.notna(w):
                        missing_std_weeks.append(str(w))
                    continue

        if missing_std_weeks:
            msg = f"Warning: Standard BW data invalid for weeks: {', '.join(missing_std_weeks[:10])}. Please update manually."
            if preview:
                all_warnings.append(msg)
            else:
                flash(msg, "warning")

        # 3. Data (Header at row 8, data from 9)
        if df_full.shape[0] > 8:
            header_row = df_full.iloc[8]
            df_data = df_full.iloc[9:].copy()
            df_data.columns = header_row
            # Reset index to have 0-based index for iterrows
            df_data.reset_index(drop=True, inplace=True)
        else:
            df_data = pd.DataFrame()
        
        # --- Column Mapping Logic ---
        headers = [str(c).upper().strip() for c in df_data.columns]

        def find_idx(candidates, default=None):
            if isinstance(candidates, str): candidates = [candidates]

            # 1. Exact Match
            for cand in candidates:
                cand = cand.upper()
                if cand in headers:
                    return headers.index(cand)

            # 2. StartsWith Match
            for cand in candidates:
                cand = cand.upper()
                for i, h in enumerate(headers):
                    if h.startswith(cand):
                        return i

            return default

        # Indices map
        idx_date = find_idx(['DATE'], 1)

        idx_cull_m = find_idx(['CULL MALE'], 2)
        idx_cull_f = find_idx(['CULL FEMALE'], 3)
        idx_dead_m = find_idx(['DEAD MALE'], 4)
        idx_dead_f = find_idx(['DEAD FEMALE'], 5)

        idx_feed_m = find_idx(['GIVEN MALE G/B', 'MALE FEED G/B'], 16)
        idx_feed_f = find_idx(['GIVEN FEMALE G/B', 'FEMALE FEED G/B'], 17)

        idx_eggs = find_idx(['EGG COLLECTED', 'EGGS COLLECTED'], 24)
        idx_jumbo = find_idx(['JUMBO'], 25)
        idx_small = find_idx(['SMALL'], 26)
        idx_abnormal = find_idx(['ABNORMAL'], 27)
        idx_crack = find_idx(['CRACK'], 28)
        idx_egg_weight = find_idx(['GRAM EGG', 'EGG WEIGHT'], 29)

        idx_bw_m = find_idx(['MALE BODY WEIGHT'], 39)
        idx_unif_m = find_idx(['MALE UNIFORMITY'], 40)
        idx_bw_f = find_idx(['FEMALE BODY WEIGHT'], 41)
        idx_unif_f = find_idx(['FEMALE UNIFORMITY'], 42)

        idx_w1 = find_idx(['8AM (m^3)', '8AM'], 43)
        idx_w2 = find_idx(['11AM (m^3)', '11AM'], 44)
        idx_w3 = find_idx(['5PM (m^3)', '5PM'], 45)

        idx_light_on = find_idx(['LIGHT ON'], 50)
        idx_light_off = find_idx(['LIGHT OFF'], 51)
        idx_feed_start = find_idx(['FEED START'], 53)
        idx_feed_end = find_idx(['FEED END'], 54)
        idx_remarks = find_idx(['REMARKS'], 56)

        partition_rows_indices = set()
        data_rows = []
        for index, row in df_data.iterrows():
            if idx_date >= len(row): continue
            date_val = row.iloc[idx_date]
            if pd.isna(date_val):
                continue
            log_date = parse_date(date_val)
            if log_date:
                data_rows.append(row)

        i = 0
        while i < len(data_rows):
            row = data_rows[i]
            # Ensure row is long enough for critical checks
            if len(row) < 2:
                i+=1
                continue

            if idx_date >= len(row):
                i+=1
                continue

            date_val = row.iloc[idx_date]
            log_date = parse_date(date_val)

            if not log_date:
                i+=1
                continue
            
            def get_float(r, idx):
                if idx is None or idx >= len(r): return 0.0
                val = r.iloc[idx]
                if pd.isna(val): return 0.0
                try: return float(val)
                except (ValueError, TypeError): return 0.0

            def get_int(r, idx):
                if idx is None or idx >= len(r): return 0
                val = r.iloc[idx]
                if pd.isna(val): return 0
                try: return int(float(val))
                except (ValueError, TypeError): return 0
                
            def get_str(r, idx):
                if idx is None or idx >= len(r): return None
                val = r.iloc[idx]
                return str(val) if pd.notna(val) else None

            def get_time(r, idx):
                if idx is None or idx >= len(r): return None
                val = r.iloc[idx]
                if pd.isna(val): return None
                if isinstance(val, str): return val
                return val.strftime('%H:%M') if hasattr(val, 'strftime') else str(val)

            # Check for Weekly Summary Rows (High Feed)
            feed_check_m = get_float(row, idx_feed_m)
            feed_check_f = get_float(row, idx_feed_f)

            if feed_check_m > 500 or feed_check_f > 500:
                # Likely a summary row with Total Feed instead of G/B
                i+=1
                continue

            log = existing_logs_dict.get(log_date)
            is_new_log = False
            if not log:
                log = DailyLog(
                    flock_id=flock_id,
                    date=log_date,                    body_weight_male=0,
                    body_weight_female=0
                )
                db.session.add(log)
                existing_logs_dict[log_date] = log
                is_new_log = True

            log.culls_male = get_int(row, idx_cull_m)
            log.culls_female = get_int(row, idx_cull_f)
            log.mortality_male = get_int(row, idx_dead_m)
            log.mortality_female = get_int(row, idx_dead_f)

            log.feed_male_gp_bird = feed_check_m
            log.feed_female_gp_bird = feed_check_f

            log.eggs_collected = get_int(row, idx_eggs)
            log.cull_eggs_jumbo = get_int(row, idx_jumbo)
            log.cull_eggs_small = get_int(row, idx_small)
            log.cull_eggs_abnormal = get_int(row, idx_abnormal)
            log.cull_eggs_crack = get_int(row, idx_crack)
            log.egg_weight = get_float(row, idx_egg_weight)

            log.water_reading_1 = get_int(row, idx_w1)
            log.water_reading_2 = get_int(row, idx_w2)
            log.water_reading_3 = get_int(row, idx_w3)

            log.light_on_time = get_time(row, idx_light_on)
            log.light_off_time = get_time(row, idx_light_off)
            log.feed_cleanup_start = get_time(row, idx_feed_start)
            log.feed_cleanup_end = get_time(row, idx_feed_end)

            val_rem = row.iloc[idx_remarks] if (idx_remarks and len(row) > idx_remarks) else None
            if pd.notna(val_rem):
                rem_str = str(val_rem).strip()
                if rem_str and rem_str.lower() not in EMPTY_NOTE_VALUES:
                    log.clinical_notes = rem_str
                else:
                    log.clinical_notes = None
            else:
                log.clinical_notes = None

            bw_m = get_float(row, idx_bw_m)
            bw_f = get_float(row, idx_bw_f)
            unif_m = get_float(row, idx_unif_m)
            unif_f = get_float(row, idx_unif_f)

            has_bw = (bw_m > 0 or bw_f > 0)

            if has_bw:
                log.is_weighing_day = True
                days_diff = (log.date - intake_date).days
                week_num = 0 if days_diff == 0 else ((days_diff - 1) // 7) + 1 if days_diff > 0 else (days_diff // 7)
                if week_num in standard_bw_map:
                    log.standard_bw_male = round_to_whole(standard_bw_map[week_num][0])
                    log.standard_bw_female = round_to_whole(standard_bw_map[week_num][1])

                log.bw_male_p1 = round_to_whole(bw_m)
                log.unif_male_p1 = unif_m
                log.bw_female_p1 = round_to_whole(bw_f)
                log.unif_female_p1 = unif_f

                if i + 1 < len(data_rows):
                    row2 = data_rows[i+1]
                    bw_m2 = get_float(row2, idx_bw_m)
                    bw_f2 = get_float(row2, idx_bw_f)
                    if bw_m2 > 0 or bw_f2 > 0:
                        log.bw_male_p2 = round_to_whole(bw_m2)
                        log.unif_male_p2 = get_float(row2, idx_unif_m)
                        log.bw_female_p2 = round_to_whole(bw_f2)
                        log.unif_female_p2 = get_float(row2, idx_unif_f)
                        partition_rows_indices.add(i+1)

                if i + 2 < len(data_rows):
                    row3 = data_rows[i+2]
                    bw_f3 = get_float(row3, idx_bw_f)
                    if bw_f3 > 0:
                        log.bw_female_p3 = round_to_whole(bw_f3)
                        log.unif_female_p3 = get_float(row3, idx_unif_f)
                        partition_rows_indices.add(i+2)

                if i + 3 < len(data_rows):
                    row4 = data_rows[i+3]
                    bw_f4 = get_float(row4, idx_bw_f)
                    if bw_f4 > 0:
                        log.bw_female_p4 = round_to_whole(bw_f4)
                        log.unif_female_p4 = get_float(row4, idx_unif_f)
                        partition_rows_indices.add(i+3)

            if i in partition_rows_indices:
                log.body_weight_male = 0
                log.body_weight_female = 0
                log.uniformity_male = 0
                log.uniformity_female = 0
                log.is_weighing_day = False
            else:
                if has_bw:
                    m_count = 0
                    m_sum = 0
                    if (log.bw_male_p1 or 0) > 0: m_sum += log.bw_male_p1; m_count += 1
                    if (log.bw_male_p2 or 0) > 0: m_sum += log.bw_male_p2; m_count += 1
                    log.body_weight_male = round_to_whole(m_sum / m_count) if m_count > 0 else 0

                    f_count = 0
                    f_sum = 0
                    if (log.bw_female_p1 or 0) > 0: f_sum += log.bw_female_p1; f_count += 1
                    if (log.bw_female_p2 or 0) > 0: f_sum += log.bw_female_p2; f_count += 1
                    if (log.bw_female_p3 or 0) > 0: f_sum += log.bw_female_p3; f_count += 1
                    if (log.bw_female_p4 or 0) > 0: f_sum += log.bw_female_p4; f_count += 1
                    log.body_weight_female = round_to_whole(f_sum / f_count) if f_count > 0 else 0

                    m_u_sum = 0
                    if (log.unif_male_p1 or 0) > 0: m_u_sum += log.unif_male_p1
                    if (log.unif_male_p2 or 0) > 0: m_u_sum += log.unif_male_p2
                    log.uniformity_male = (m_u_sum / m_count) if m_count > 0 else 0

                    f_u_sum = 0
                    if (log.unif_female_p1 or 0) > 0: f_u_sum += log.unif_female_p1
                    if (log.unif_female_p2 or 0) > 0: f_u_sum += log.unif_female_p2
                    if (log.unif_female_p3 or 0) > 0: f_u_sum += log.unif_female_p3
                    if (log.unif_female_p4 or 0) > 0: f_u_sum += log.unif_female_p4
                    log.uniformity_female = (f_u_sum / f_count) if f_count > 0 else 0

            if preview:
                # Capture change for preview
                changes.append({
                    'date': log.date.strftime('%Y-%m-%d'),
                    'house': house_name,
                    'flock': flock_uid_str if 'flock_uid_str' in locals() else f"New Flock {house_name}",
                    'type': 'New' if is_new_log else 'Update',
                    'mortality_male': log.mortality_male,
                    'mortality_female': log.mortality_female,
                    'culls_male': log.culls_male,
                    'culls_female': log.culls_female,
                    'eggs': log.eggs_collected,
                    'feed_male_gp_bird': log.feed_male_gp_bird,
                    'feed_female_gp_bird': log.feed_female_gp_bird,
                    'water_reading_1': log.water_reading_1
                })

            i += 1

        if commit:
            safe_commit()
        else:
            db.session.flush()
        
        all_logs = sorted(existing_logs_dict.values(), key=lambda x: x.date)
        for i, log in enumerate(all_logs):
            if i > 0:
                prev_log = all_logs[i-1]
                if prev_log.water_reading_1 and log.water_reading_1:
                    r1_today = log.water_reading_1 / 100.0
                    r1_prev = prev_log.water_reading_1 / 100.0
                    # The intake belongs to the previous day
                    prev_log.water_intake_calculated = (r1_today - r1_prev) * 1000.0
                    db.session.add(prev_log)

                    # Ensure current log resets if not evaluated by the next day yet
                    log.water_intake_calculated = 0.0
                    db.session.add(log)

        if commit:
            safe_commit()
        else:
            db.session.flush()

        flock_obj = Flock.query.get(flock_id)
        warnings = verify_import_data(flock_obj, logs=all_logs)
        if warnings:
            if preview:
                all_warnings.extend(warnings)
            else:
                flash(f"Import Verification Warnings for {house_name}: {'; '.join(warnings[:3])}...", 'warning')

    if preview:
        db.session.rollback()
        return changes, all_warnings

def recalculate_flock_inventory(flock_id):
    """
    Recalculates males_at_start, females_at_start, and recalculates feed requirements
    by iterating chronologically from the start of the flock to avoid repetitive
    summation queries.
    """
    flock = Flock.query.get(flock_id)
    if not flock:
        return

    # Fetch all logs in order
    logs = DailyLog.query.filter_by(flock_id=flock_id).order_by(DailyLog.date.asc()).all()

    curr_males = flock.intake_male or 0
    curr_females = flock.intake_female or 0
    prev_log = None

    for log in logs:
        # Update start of day columns
        log.males_at_start = curr_males
        log.females_at_start = curr_females

        # Recalculate water intake
        if prev_log and (log.date - prev_log.date).days == 1 and log.water_reading_1 is not None and prev_log.water_reading_1 is not None:
            r1_today = log.water_reading_1 / 100.0
            r1_prev = prev_log.water_reading_1 / 100.0
            # Save the calculated intake on the previous day since the 24h consumption belongs to it
            prev_log.water_intake_calculated = (r1_today - r1_prev) * 1000.0

            # Reset current day's intake until tomorrow's reading is available
            log.water_intake_calculated = 0.0
        else:
            if not log.water_intake_calculated:
                log.water_intake_calculated = 0.0

        prev_log = log

        # Feed Multiplier Logic
        multiplier = 1.0
        if log.feed_program == 'Skip-a-day':
            multiplier = 2.0
        elif log.feed_program == '2/1':
            multiplier = 1.5


        # Update stock for the next day
        # Only mortality and culls affect total house stock.
        curr_males -= ((log.mortality_male or 0) + (log.culls_male or 0))
        curr_females -= ((log.mortality_female or 0) + (log.culls_female or 0))

    safe_commit()


def check_daily_log_completion(farm_id, selected_date):
    """
    Checks the DailyLog table for the current farm_id and selected_date.
    Returns a list of dictionaries with house info and completion status.
    If farm_id is None, returns all active flocks across the entire system.
    """
    if not selected_date:
        return []

    # Get active flocks for the given farm, or all active flocks if farm_id is None
    query = Flock.query.join(House).filter(Flock.status == 'Active')
    if farm_id:
        query = query.filter(Flock.farm_id == farm_id)

    active_flocks = query.order_by(House.name).all()

    # Pre-fetch daily logs for these flocks on the selected date
    flock_ids = [f.id for f in active_flocks]
    logs_today = DailyLog.query.filter(
        DailyLog.flock_id.in_(flock_ids),
        DailyLog.date == selected_date
    ).all()
    logs_map = {l.flock_id: l for l in logs_today}

    status_list = []
    for f in active_flocks:
        is_done = f.id in logs_map
        status_list.append({
            'id': f.house_id,
            'name': f.house.name,
            'is_done': is_done
        })

    return status_list

def update_log_from_request(log, req):
    old_data = {
        'mortality_male': log.mortality_male,
        'mortality_female': log.mortality_female,
        'culls_male': log.culls_male,
        'culls_female': log.culls_female,
        'feed_male_gp_bird': log.feed_male_gp_bird,
        'feed_female_gp_bird': log.feed_female_gp_bird,
        'eggs_collected': log.eggs_collected,
        'cull_eggs_jumbo': log.cull_eggs_jumbo,
        'cull_eggs_small': log.cull_eggs_small,
        'cull_eggs_crack': log.cull_eggs_crack,
        'cull_eggs_abnormal': log.cull_eggs_abnormal,
        'water_reading_1': log.water_reading_1
    }

    log.mortality_male = int(req.form.get('mortality_male') or 0)
    log.mortality_female = int(req.form.get('mortality_female') or 0)
    log.mortality_male_hosp = int(req.form.get('mortality_male_hosp') or 0)
    log.mortality_female_hosp = int(req.form.get('mortality_female_hosp') or 0)
    log.culls_male_hosp = int(req.form.get('culls_male_hosp') or 0)
    log.culls_female_hosp = int(req.form.get('culls_female_hosp') or 0)
    log.culls_male = int(req.form.get('culls_male') or 0)
    log.culls_female = int(req.form.get('culls_female') or 0)
    log.males_moved_to_prod = int(req.form.get('males_moved_to_prod') or 0)
    log.males_moved_to_hosp = int(req.form.get('males_moved_to_hosp') or 0)
    log.females_moved_to_prod = int(req.form.get('females_moved_to_prod') or 0)
    log.females_moved_to_hosp = int(req.form.get('females_moved_to_hosp') or 0)

    log.feed_program = req.form.get('feed_program')

    fc_m_id = req.form.get('feed_code_male_id')
    log.feed_code_male_id = int(fc_m_id) if fc_m_id else None

    fc_f_id = req.form.get('feed_code_female_id')
    log.feed_code_female_id = int(fc_f_id) if fc_f_id else None

    # Fallback if only single select used (legacy)
    fc_id = req.form.get('feed_code_id')
    if fc_id and not log.feed_code_male_id:
         log.feed_code_male_id = int(fc_id)
    if fc_id and not log.feed_code_female_id:
         log.feed_code_female_id = int(fc_id)

    log.feed_male_gp_bird = float(req.form.get('feed_male_gp_bird') or 0)
    log.feed_female_gp_bird = float(req.form.get('feed_female_gp_bird') or 0)

    # Fetch logs before today to sum mortality
    # We query once and sum in Python to avoid N+1 and slow sum queries
    previous_logs = DailyLog.query.filter(
        DailyLog.flock_id == log.flock_id,
        DailyLog.date < log.date
    ).order_by(DailyLog.date.asc()).all()

    cum_mort_m = 0
    cum_culls_m = 0
    cum_mort_f = 0
    cum_culls_f = 0

    for prev_log in previous_logs:
        cum_mort_m += (prev_log.mortality_male or 0)
        cum_culls_m += (prev_log.culls_male or 0)
        cum_mort_f += (prev_log.mortality_female or 0)
        cum_culls_f += (prev_log.culls_female or 0)

    # Transfers logic: If moved to hosp, they are out of prod.
    # But wait, males in hosp still eat?
    # Assuming "Feed Male" covers all males in the house (Prod + Hosp)?
    # Usually feed is tracked per house.
    # If so, we just need Total Males Alive in House.
    # Total Alive = Intake - Total Dead - Total Culled.
    # Transfers between pens (Prod <-> Hosp) don't change house population.
    # Let's assume total stock in house.

    start_m = log.flock.intake_male or 0
    start_f = log.flock.intake_female or 0

    current_stock_m = start_m - cum_mort_m - cum_culls_m
    current_stock_f = start_f - cum_mort_f - cum_culls_f

    # Data Integrity: Validation Layer
    if log.mortality_male + log.culls_male > current_stock_m:
        raise ValueError(f"Male reductions (Mortality + Culls: {log.mortality_male + log.culls_male}) exceeds Current Stock ({current_stock_m}).")
    if log.mortality_female + log.culls_female > current_stock_f:
        raise ValueError(f"Female reductions (Mortality + Culls: {log.mortality_female + log.culls_female}) exceeds Current Stock ({current_stock_f}).")

    # Automated Alerts: Mortality Spike
    alert_triggered = False
    mort_pct_m = 0.0
    mort_pct_f = 0.0
    egg_prod_pct = 0.0

    if current_stock_m > 0:
        mort_pct_m = (log.mortality_male / current_stock_m) * 100
        if mort_pct_m > 0.5:
            flash(f"ALERT: High Male Mortality Spike ({mort_pct_m:.2f}%) detected!", "danger")
            alert_triggered = True

    if current_stock_f > 0:
        mort_pct_f = (log.mortality_female / current_stock_f) * 100
        if mort_pct_f > 0.5:
            flash(f"ALERT: High Female Mortality Spike ({mort_pct_f:.2f}%) detected!", "danger")
            alert_triggered = True

    if current_stock_f > 0 and getattr(log, 'eggs_collected', 0) > 0:
        egg_prod_pct = (log.eggs_collected / current_stock_f) * 100

    if alert_triggered:
        # Simulate sending email
        app.logger.warning(f"Mortality Alert Triggered for Flock {log.flock_id}")

    # Phase 5: Dynamic Push Alerts
    active_rules = NotificationRule.query.filter_by(is_active=True).all()
    triggered_rules = []

    metric_values = {
        'mortality_female_pct': mort_pct_f,
        'mortality_male_pct': mort_pct_m,
        'egg_production_pct': egg_prod_pct
    }

    for rule in active_rules:
        val = metric_values.get(rule.metric)
        if val is not None:
            # Evaluate operator
            if rule.operator == '>':
                is_triggered = val > rule.threshold
            elif rule.operator == '<':
                is_triggered = val < rule.threshold
            elif rule.operator == '>=':
                is_triggered = val >= rule.threshold
            elif rule.operator == '<=':
                is_triggered = val <= rule.threshold
            elif rule.operator == '==':
                is_triggered = val == rule.threshold
            else:
                is_triggered = False

            if is_triggered:
                triggered_rules.append(rule)

    if triggered_rules:
        house_name = log.flock.house.name if log.flock and log.flock.house else "Unknown House"
        for rule in triggered_rules:
            title = f"Alert: {rule.name}"
            metric_label = METRIC_LABELS.get(rule.metric, rule.metric)
            body = f"{house_name}: {rule.name} Alert! {metric_label} is {metric_values.get(rule.metric):.2f}% (Threshold: {rule.operator} {rule.threshold}%)"

            # Notify all users
            all_users = User.query.all()
            for user in all_users:
                try:
                    # Provide a URL to deep link to the flock detail
                    alert_url = url_for('view_flock', id=log.flock.id) if log.flock else '/'
                    send_push_alert(user.id, title, body, url=alert_url)
                except Exception as e:
                    app.logger.error(f"Failed to send push alert to {user.username}: {str(e)}")

    # Feed Guardian Validation
    override = req.form.get('override_validation') == 'true'
    is_feeding_attempt = log.feed_male_gp_bird > 0 or log.feed_female_gp_bird > 0

    if is_feeding_attempt and not override:
        from datetime import timedelta
        if log.feed_program == 'Skip-a-day':
            yesterday_log = DailyLog.query.filter_by(flock_id=log.flock_id, date=log.date - timedelta(days=1)).first()
            if yesterday_log and (yesterday_log.feed_male_gp_bird > 0 or yesterday_log.feed_female_gp_bird > 0):
                raise ValueError("Invalid Entry: Yesterday was an ON-day. Today must be a Fasting Day (0g) for Skip-a-Day program.")
        elif log.feed_program == '2/1':
            yesterday_log = DailyLog.query.filter_by(flock_id=log.flock_id, date=log.date - timedelta(days=1)).first()
            day_minus_2_log = DailyLog.query.filter_by(flock_id=log.flock_id, date=log.date - timedelta(days=2)).first()

            y_fed = yesterday_log and (yesterday_log.feed_male_gp_bird > 0 or yesterday_log.feed_female_gp_bird > 0)
            d2_fed = day_minus_2_log and (day_minus_2_log.feed_male_gp_bird > 0 or day_minus_2_log.feed_female_gp_bird > 0)

            if y_fed and d2_fed:
                raise ValueError("Invalid Entry: The last 2 days were ON-days. Today must be a Fasting Day (0g) for 2/1 program.")

    # Feed Multiplier Logic
    multiplier = 1.0
    if log.feed_program == 'Skip-a-day':
        multiplier = 2.0
    elif log.feed_program == '2/1':
        multiplier = 1.5

    # Calculate Total Kg
    # Formula: (g/bird * multiplier * stock) / 1000
    # Calculations are now done on the fly in metrics.py

    log.eggs_collected = int(req.form.get('eggs_collected') or 0)
    log.cull_eggs_jumbo = int(req.form.get('cull_eggs_jumbo') or 0)
    log.cull_eggs_small = int(req.form.get('cull_eggs_small') or 0)
    log.cull_eggs_abnormal = int(req.form.get('cull_eggs_abnormal') or 0)
    log.cull_eggs_crack = int(req.form.get('cull_eggs_crack') or 0)
    log.egg_weight = float(req.form.get('egg_weight') or 0)

    bw_m_val = float(req.form.get('body_weight_male') or 0)
    bw_f_val = float(req.form.get('body_weight_female') or 0)
    uni_m_val = float(req.form.get('uniformity_male') or 0)
    uni_f_val = float(req.form.get('uniformity_female') or 0)

    if log.flock.phase == 'Rearing':
        PartitionWeight.query.filter_by(log_id=log.id).delete()

        f_parts = [f'F{i}' for i in range(1, 9)]
        m_parts = [f'M{i}' for i in range(1, 9)]

        sum_bw_f = 0; count_bw_f = 0
        sum_uni_f = 0; count_uni_f = 0
        sum_bw_m = 0; count_bw_m = 0
        sum_uni_m = 0; count_uni_m = 0

        for p in f_parts + m_parts:
            bw = float(req.form.get(f'bw_{p}') or 0)
            uni = float(req.form.get(f'uni_{p}') or 0)

            if bw > 0:
                bw_whole = round_to_whole(bw)
                pw = PartitionWeight(log_id=log.id, partition_name=p, body_weight=bw_whole, uniformity=uni)
                db.session.add(pw)

                if p.startswith('F'):
                    sum_bw_f += bw_whole; count_bw_f += 1
                    if uni > 0: sum_uni_f += uni; count_uni_f += 1
                else:
                    sum_bw_m += bw_whole; count_bw_m += 1
                    if uni > 0: sum_uni_m += uni; count_uni_m += 1

        if count_bw_f > 0: bw_f_val = sum_bw_f / count_bw_f
        if count_uni_f > 0: uni_f_val = sum_uni_f / count_uni_f
        if count_bw_m > 0: bw_m_val = sum_bw_m / count_bw_m
        if count_uni_m > 0: uni_m_val = sum_uni_m / count_uni_m

    log.body_weight_male = round_to_whole(bw_m_val)
    log.body_weight_female = round_to_whole(bw_f_val)
    log.uniformity_male = uni_m_val if uni_m_val > 1.0 else (uni_m_val * 100) if uni_m_val > 0 else 0
    log.uniformity_female = uni_f_val if uni_f_val > 1.0 else (uni_f_val * 100) if uni_f_val > 0 else 0

    log.is_weighing_day = 'is_weighing_day' in req.form
    log.bw_male_p1 = round_to_whole(req.form.get('bw_M1'))
    log.bw_male_p2 = round_to_whole(req.form.get('bw_M2'))
    log.unif_male_p1 = float(req.form.get('uni_M1') or 0)
    log.unif_male_p2 = float(req.form.get('uni_M2') or 0)
    log.bw_female_p1 = round_to_whole(req.form.get('bw_F1'))
    log.bw_female_p2 = round_to_whole(req.form.get('bw_F2'))
    log.bw_female_p3 = round_to_whole(req.form.get('bw_F3'))
    log.bw_female_p4 = round_to_whole(req.form.get('bw_F4'))
    log.unif_female_p1 = float(req.form.get('uni_F1') or 0)
    log.unif_female_p2 = float(req.form.get('uni_F2') or 0)
    log.unif_female_p3 = float(req.form.get('uni_F3') or 0)
    log.unif_female_p4 = float(req.form.get('uni_F4') or 0)
    log.standard_bw_male = round_to_whole(req.form.get('standard_bw_male'))
    log.standard_bw_female = round_to_whole(req.form.get('standard_bw_female'))

    log.water_reading_1 = int(req.form.get('water_reading_1') or 0)
    log.water_reading_2 = int(req.form.get('water_reading_2') or 0)
    log.water_reading_3 = int(req.form.get('water_reading_3') or 0)
    log.flushing = True if req.form.get('flushing') else False
    log.selection_done = True if req.form.get('selection_done') else False
    log.spiking = True if req.form.get('spiking') else False

    log.light_on_time = req.form.get('light_on_time')
    log.light_off_time = req.form.get('light_off_time')
    log.feed_cleanup_start = req.form.get('feed_cleanup_start')
    log.feed_cleanup_end = req.form.get('feed_cleanup_end')

    # Only remarks is processed in the main daily log now (since clinical notes/post mortem was separated)
    remarks_val = req.form.get('remarks')
    if remarks_val and remarks_val.strip() and remarks_val.strip().lower() not in EMPTY_NOTE_VALUES:
        log.remarks = remarks_val.strip()
    else:
        log.remarks = None

    if 'photo' in req.files:
        files = req.files.getlist('photo')
        for file in files:
            if file and file.filename != '':
                date_str = log.date.strftime('%y%m%d')
                raw_name = f"{log.flock.flock_id}_{date_str}_{file.filename}"
                filename = secure_filename(raw_name)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)

                new_photo = DailyLogPhoto(
                    log_id=log.id,
                    file_path=filepath,
                    original_filename=file.filename
                )
                db.session.add(new_photo)

    from datetime import timedelta
    yesterday = log.date - timedelta(days=1)
    yesterday_log = DailyLog.query.filter_by(flock_id=log.flock_id, date=yesterday).first()

    # Update previous day's water consumption since the 24h period finishes today
    if yesterday_log:
        r1_today_real = log.water_reading_1 / 100.0
        r1_yesterday_real = yesterday_log.water_reading_1 / 100.0
        yesterday_log.water_intake_calculated = (r1_today_real - r1_yesterday_real) * 1000.0

    # Today's consumption is 0 until tomorrow's reading
    log.water_intake_calculated = 0.0

    update_clinical_notes(log, req)

    new_data = {
        'mortality_male': log.mortality_male,
        'mortality_female': log.mortality_female,
        'culls_male': log.culls_male,
        'culls_female': log.culls_female,
        'feed_male_gp_bird': log.feed_male_gp_bird,
        'feed_female_gp_bird': log.feed_female_gp_bird,
        'eggs_collected': log.eggs_collected,
        'cull_eggs_jumbo': log.cull_eggs_jumbo,
        'cull_eggs_small': log.cull_eggs_small,
        'cull_eggs_crack': log.cull_eggs_crack,
        'cull_eggs_abnormal': log.cull_eggs_abnormal,
        'water_reading_1': log.water_reading_1
    }

    changes = {k: {'old': old_data[k], 'new': new_data[k]} for k in old_data if old_data[k] != new_data[k]}
    if changes:
        log_user_activity(current_user.id, 'Edit', 'DailyLog', log.id, details=changes)

def save_note_photos(log, note, files):
    for file in files:
        if file and file.filename != '':
            date_str = log.date.strftime('%y%m%d')
            # Ensure safe filename
            safe_orig = secure_filename(file.filename)
            raw_name = f"{log.flock.flock_id}_{date_str}_Note{note.id}_{safe_orig}"
            filename = secure_filename(raw_name)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            new_photo = DailyLogPhoto(
                log_id=log.id,
                note_id=note.id,
                file_path=filepath,
                original_filename=file.filename
            )
            db.session.add(new_photo)

def update_clinical_notes(log, req):
    # 1. Handle Deletions
    del_ids = req.form.getlist('delete_note_ids[]')
    if del_ids:
        # Check ownership/relation
        ClinicalNote.query.filter(ClinicalNote.id.in_(del_ids), ClinicalNote.log_id == log.id).delete(synchronize_session=False)

    # 2. Handle Existing Updates
    exist_ids = req.form.getlist('existing_note_id[]')

    int_exist_ids = [int(nid) for nid in exist_ids if str(nid).isdigit()]
    existing_notes = ClinicalNote.query.filter(ClinicalNote.id.in_(int_exist_ids), ClinicalNote.log_id == log.id).all()
    notes_dict = {str(note.id): note for note in existing_notes}

    for nid in exist_ids:
        note = notes_dict.get(str(nid))
        if note:
            caption = req.form.get(f'existing_note_caption_{nid}')
            if caption is not None:
                note.caption = caption

            # Photos
            if f'existing_note_photos_{nid}' in req.files:
                files = req.files.getlist(f'existing_note_photos_{nid}')
                save_note_photos(log, note, files)

    # 3. Handle New Notes
    new_indices = req.form.getlist('extra_note_index[]')
    for idx in new_indices:
        caption = req.form.get(f'extra_note_caption_{idx}')
        # Check files
        files = req.files.getlist(f'extra_note_photos_{idx}')
        has_files = any(f.filename != '' for f in files)

        if caption or has_files:
            note = ClinicalNote(log_id=log.id, caption=caption)
            db.session.add(note)
            db.session.flush() # Get ID

            if has_files:
                save_note_photos(log, note, files)

def verify_import_data(flock, logs=None):
    weekly_records = ImportedWeeklyBenchmark.query.filter_by(flock_id=flock.id).order_by(ImportedWeeklyBenchmark.week).all()
    if logs is None:
        logs = DailyLog.query.filter_by(flock_id=flock.id).all()

    warnings = []
    agg = {}
    for log in logs:
        delta = (log.date - flock.intake_date).days
        week = 0 if delta == 0 else ((delta - 1) // 7) + 1 if delta > 0 else (delta // 7)
        if week not in agg:
            agg[week] = {'mort_f': 0, 'eggs': 0}

        agg[week]['mort_f'] += log.mortality_female
        agg[week]['eggs'] += log.eggs_collected

    for wd in weekly_records:
        if wd.week in agg:
            calc = agg[wd.week]
            if abs(calc['mort_f'] - wd.mortality_female) > 1:
                warnings.append(f"Week {wd.week}: Calc Mort F ({calc['mort_f']}) != Imported ({wd.mortality_female})")

            if abs(calc['eggs'] - wd.eggs_collected) > 5:
                warnings.append(f"Week {wd.week}: Calc Eggs ({calc['eggs']}) != Imported ({wd.eggs_collected})")

    return warnings

@app.route('/health_log')
def health_log():
    return redirect(url_for('health_log_vaccines'))

@app.route('/health_log/vaccines', methods=['GET', 'POST'])
def health_log_vaccines():
    today = date.today()
    try:
        year = int(request.args.get('year', today.year))
        month = int(request.args.get('month', today.month))
    except:
        year = today.year
        month = today.month

    selected_flock_id = request.args.get('flock_id')
    edit_flock_id = request.args.get('edit_flock_id', type=int)

    if request.method == 'POST':
        flock_id_param = request.form.get('flock_id') or selected_flock_id

        if 'add_vaccine_row' in request.form:
            if flock_id_param:
                v = Vaccine(flock_id=flock_id_param, age_code='', vaccine_name='')
                db.session.add(v)
                safe_commit()
                flash('New vaccine row added.', 'success')

        elif 'load_vaccine_standard' in request.form:
            if flock_id_param:
                if Vaccine.query.filter_by(flock_id=flock_id_param).count() == 0:
                    initialize_vaccine_schedule(flock_id_param)
                    flash('Standard vaccine schedule loaded.', 'success')
                else:
                    flash('Vaccine schedule is not empty. Cannot load standard.', 'warning')

        elif 'delete_vaccine_id' in request.form:
            v_id = request.form.get('delete_vaccine_id')
            v = Vaccine.query.get(v_id)
            if v:
                db.session.delete(v)
                safe_commit()
                flash('Vaccine record deleted.', 'info')

        elif 'save_changes' in request.form:
            # Bulk Update
            vaccine_ids = [k.split('_')[2] for k in request.form.keys() if k.startswith('v_id_')]
            updated_count = 0

            int_vids = [int(vid) for vid in vaccine_ids if vid.isdigit()]
            vaccines = Vaccine.query.filter(Vaccine.id.in_(int_vids), Vaccine.flock_id == id).all()
            vaccine_dict = {str(vac.id): vac for vac in vaccines}

            for vid in vaccine_ids:
                v = vaccine_dict.get(vid)
                if not v: continue

                age_code = request.form.get(f'age_code_{vid}')
                name = request.form.get(f'vaccine_name_{vid}')
                route = request.form.get(f'route_{vid}')
                est_date_str = request.form.get(f'est_date_{vid}')
                actual_date_str = request.form.get(f'actual_date_{vid}')
                remarks = request.form.get(f'remarks_{vid}')

                try:
                    dpu = int(request.form.get(f'doses_per_unit_{vid}') or 1000)
                    v.doses_per_unit = dpu
                except: pass

                if age_code is not None: v.age_code = age_code
                if name is not None: v.vaccine_name = name
                if route is not None: v.route = route
                if remarks is not None: v.remarks = remarks

                if est_date_str:
                    try:
                        v.est_date = datetime.strptime(est_date_str, '%Y-%m-%d').date()
                    except ValueError: pass

                if actual_date_str:
                    try:
                        v.actual_date = datetime.strptime(actual_date_str, '%Y-%m-%d').date()
                    except ValueError: pass
                elif actual_date_str == '':
                    v.actual_date = None

                updated_count += 1

            safe_commit()
            flash(f'Updated {updated_count} records.', 'success')

        return redirect(url_for('health_log_vaccines', year=year, month=month, flock_id=flock_id_param, edit_flock_id=edit_flock_id))

    cal = calendar.Calendar(firstweekday=6)
    month_days = cal.monthdatescalendar(year, month)

    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    start_date = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end_date = date(year, month, last_day)

    active_flocks = Flock.query.filter_by(status='Active').options(joinedload(Flock.house)).all()
    for f in active_flocks:
        days = (today - f.intake_date).days
        f.current_week = 0 if days == 0 else ((days - 1) // 7) + 1 if days > 0 else 0
    flock_ids = [f.id for f in active_flocks]

    vaccine_events_by_date = {}
    vaccines = Vaccine.query.filter(Vaccine.flock_id.in_(flock_ids)).filter(Vaccine.est_date >= start_date, Vaccine.est_date <= end_date).all()
    for v in vaccines:
        d = v.est_date
        if d not in vaccine_events_by_date: vaccine_events_by_date[d] = []
        age_days = (d - v.flock.intake_date).days
        age_week = 0 if age_days == 0 else ((age_days - 1) // 7) + 1 if age_days > 0 else (age_days // 7)
        vaccine_events_by_date[d].append({'type': 'Vaccine', 'obj': v, 'flock': v.flock, 'age': age_week})

    flock_tasks = {}
    target_flocks = [f for f in active_flocks if str(f.id) == selected_flock_id] if selected_flock_id else active_flocks

    target_flock_ids = [f.id for f in target_flocks]

    # Bulk fetch vaccines
    all_vaccines = Vaccine.query.filter(Vaccine.flock_id.in_(target_flock_ids)).order_by(Vaccine.est_date).all()
    vaccines_by_flock = {}
    for v in all_vaccines:
        if v.flock_id not in vaccines_by_flock:
            vaccines_by_flock[v.flock_id] = []
        vaccines_by_flock[v.flock_id].append(v)

    # Bulk fetch stock history
    bulk_stock_history = get_flock_stock_history_bulk(target_flocks)

    for f in target_flocks:
        vaccines_list = vaccines_by_flock.get(f.id, [])
        stock_history = bulk_stock_history.get(f.id, {})
        sorted_dates = sorted([d for d in stock_history.keys() if isinstance(d, date)])

        for v in vaccines_list:
            target_date = v.est_date or date.today()
            applicable_stock = f.intake_male + f.intake_female
            best_date = None
            for d in sorted_dates:
                if d <= target_date: best_date = d
                else: break
            if best_date:
                applicable_stock = stock_history[best_date]

            v.calculated_dose_count = v.dose_count(applicable_stock)
            v.calculated_units_needed = v.units_needed(applicable_stock)

        flock_tasks[f] = {'vaccines': vaccines_list}

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render_template('partials/health_log_calendar.html',
            show_vaccine=True,
            today=today,
            year=year,
            month=month,
            month_name=calendar.month_name[month],
            month_days=month_days,
            prev_month=prev_month, prev_year=prev_year,
            next_month=next_month, next_year=next_year,
            vaccine_events_by_date=vaccine_events_by_date,
            selected_flock_id=int(selected_flock_id) if selected_flock_id else None
        )

    return render_template('health_log_vaccine.html',
        show_vaccine=True,
        today=today,
        year=year,
        month=month,
        month_name=calendar.month_name[month],
        month_days=month_days,
        prev_month=prev_month, prev_year=prev_year,
        next_month=next_month, next_year=next_year,
        vaccine_events_by_date=vaccine_events_by_date,
        active_flocks=active_flocks,
        selected_flock_id=int(selected_flock_id) if selected_flock_id else None,
        edit_flock_id=edit_flock_id,
        flock_tasks=flock_tasks
    )

@app.route('/health_log/sampling', methods=['GET', 'POST'])
def health_log_sampling():
    today = date.today()
    try:
        year = int(request.args.get('year', today.year))
        month = int(request.args.get('month', today.month))
    except:
        year = today.year
        month = today.month

    selected_flock_id = request.args.get('flock_id')
    edit_flock_id = request.args.get('edit_flock_id', type=int)

    if request.method == 'POST':
        updated_count = 0
        s_ids = set()
        for key in request.form:
            if key.startswith('s_') and key.split('_')[-1].isdigit():
                s_ids.add(int(key.split('_')[-1]))

        sampling_events = SamplingEvent.query.filter(SamplingEvent.id.in_(s_ids)).all() if s_ids else []
        sampling_dict = {event.id: event for event in sampling_events}

        for sid in s_ids:
            s = sampling_dict.get(sid)
            if not s: continue

            test = request.form.get(f's_test_{sid}')
            if test and s.test_type != test: s.test_type = test; updated_count += 1

            age_str = request.form.get(f's_age_{sid}')
            date_str = request.form.get(f's_date_{sid}')

            new_age = int(age_str) if age_str else s.age_week
            new_date = s.scheduled_date
            if date_str:
                try:
                    new_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                except: pass

            age_changed = (new_age != s.age_week)
            date_changed = (new_date != s.scheduled_date)

            if age_changed and not date_changed:
                s.age_week = new_age
                s.scheduled_date = s.flock.intake_date + timedelta(days=((new_age-1)*7 + 1))
                updated_count += 1
            elif date_changed:
                s.scheduled_date = new_date
                diff = (new_date - s.flock.intake_date).days
                s.age_week = 0 if diff == 0 else ((diff - 1) // 7) + 1 if diff > 0 else (diff // 7)
                updated_count += 1

            actual_str = request.form.get(f's_actual_date_{sid}')
            if actual_str:
                try:
                    new_actual = datetime.strptime(actual_str, '%Y-%m-%d').date()
                    if s.actual_date != new_actual:
                        s.actual_date = new_actual
                        updated_count += 1
                except: pass
            elif actual_str == '' and s.actual_date is not None:
                s.actual_date = None
                updated_count += 1

            # Update Status
            new_status = 'Pending'
            if s.actual_date or s.result_file:
                new_status = 'Completed'
            if s.status != new_status:
                s.status = new_status
                updated_count += 1


        if updated_count > 0:
            safe_commit()
            flash(f'Updated {updated_count} records.', 'success')

        flock_id_param = request.form.get('flock_id') or selected_flock_id

        return redirect(url_for('health_log_sampling', year=year, month=month, flock_id=flock_id_param, edit_flock_id=edit_flock_id))

    cal = calendar.Calendar(firstweekday=6)
    month_days = cal.monthdatescalendar(year, month)

    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    start_date = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end_date = date(year, month, last_day)

    active_flocks = Flock.query.filter_by(status='Active').options(joinedload(Flock.house)).all()
    for f in active_flocks:
        days = (today - f.intake_date).days
        f.current_week = 0 if days == 0 else ((days - 1) // 7) + 1 if days > 0 else 0
    flock_ids = [f.id for f in active_flocks]

    sampling_events_by_date = {}
    samplings = SamplingEvent.query.filter(SamplingEvent.flock_id.in_(flock_ids)).filter(SamplingEvent.scheduled_date >= start_date, SamplingEvent.scheduled_date <= end_date).all()
    for s in samplings:
        d = s.scheduled_date
        if d:
             if d not in sampling_events_by_date: sampling_events_by_date[d] = []
             sampling_events_by_date[d].append({'type': 'Sampling', 'obj': s, 'flock': s.flock, 'age': s.age_week})

    flock_tasks = {}
    target_flocks = [f for f in active_flocks if str(f.id) == selected_flock_id] if selected_flock_id else active_flocks

    for f in target_flocks:
        flock_tasks[f] = {'sampling': SamplingEvent.query.filter_by(flock_id=f.id).order_by(SamplingEvent.age_week).all()}

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render_template('partials/health_log_calendar.html',
            show_sampling=True,
            today=today,
            year=year,
            month=month,
            month_name=calendar.month_name[month],
            month_days=month_days,
            prev_month=prev_month, prev_year=prev_year,
            next_month=next_month, next_year=next_year,
            sampling_events_by_date=sampling_events_by_date,
            selected_flock_id=int(selected_flock_id) if selected_flock_id else None
        )

    # Fetch Inventory
    medication_inventory = InventoryItem.query.filter_by(type='Medication').order_by(InventoryItem.name).all()
    vaccine_inventory = InventoryItem.query.filter_by(type='Vaccine').order_by(InventoryItem.name).all()

    return render_template('health_log_sampling.html',
        show_sampling=True,
        today=today,
        year=year,
        month=month,
        month_name=calendar.month_name[month],
        month_days=month_days,
        prev_month=prev_month, prev_year=prev_year,
        next_month=next_month, next_year=next_year,
        sampling_events_by_date=sampling_events_by_date,
        active_flocks=active_flocks,
        selected_flock_id=int(selected_flock_id) if selected_flock_id else None,
        flock_tasks=flock_tasks,
        medication_inventory=medication_inventory,
        vaccine_inventory=vaccine_inventory,
        edit_flock_id=edit_flock_id
    )

@app.route('/health_log/medication', methods=['GET', 'POST'])
def health_log_medication():
    malaysia_tz = pytz.timezone('Asia/Kuala_Lumpur')
    today = datetime.now(malaysia_tz).date()
    selected_flock_id = request.args.get('flock_id')
    edit_flock_id = request.args.get('edit_flock_id', type=int)

    if request.method == 'POST':
        flock_id_param = request.form.get('flock_id') or selected_flock_id

        if 'delete_medication_id' in request.form:
            try:
                m_id = int(request.form.get('delete_medication_id'))
                m = Medication.query.get(m_id)
                if m:
                    db.session.delete(m)
                    safe_commit()
                    flash('Medication record deleted.', 'info')
            except Exception as e:
                db.session.rollback()
                flash(f'Error deleting medication: {str(e)}', 'danger')
            return redirect(url_for('health_log_medication', flock_id=flock_id_param, edit_flock_id=edit_flock_id))

        if 'add_medication' in request.form:
             if flock_id_param:
                 try:
                     s_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
                     e_date = None
                     if request.form.get('end_date'):
                         e_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()

                     inv_id = request.form.get('inventory_item_id')
                     drug_name = request.form.get('drug_name')

                     item = None
                     if inv_id and inv_id.isdigit():
                         inv_id = int(inv_id)
                         item = db.session.get(InventoryItem, inv_id)
                         if item: drug_name = item.name
                     else:
                         inv_id = None

                     qty = 0.0
                     if request.form.get('amount_used_qty'):
                         try: qty = float(request.form.get('amount_used_qty'))
                         except: pass

                     m = Medication(
                         flock_id=flock_id_param,
                         drug_name=drug_name,
                         inventory_item_id=inv_id,
                         dosage=request.form.get('dosage'),
                         amount_used=request.form.get('amount_used'),
                         amount_used_qty=qty,
                         start_date=s_date,
                         end_date=e_date,
                         remarks=request.form.get('remarks')
                     )
                     db.session.add(m)

                     if inv_id and qty > 0 and item:
                         item.current_stock -= qty
                         t = InventoryTransaction(
                             inventory_item_id=inv_id,
                             transaction_type='Usage',
                             quantity=qty,
                             transaction_date=s_date,
                             notes=f'Used in Health Log'
                         )
                         db.session.add(t)

                     safe_commit()
                     flash('Medication added.', 'success')
                 except Exception as e:
                     flash(f'Error adding medication: {str(e)}', 'danger')

        updated_count = 0
        m_ids = set()
        for key in request.form:
            if key.startswith('m_') and key.split('_')[-1].isdigit():
                m_ids.add(int(key.split('_')[-1]))

        medications = Medication.query.filter(Medication.id.in_(m_ids)).all() if m_ids else []
        medication_dict = {med.id: med for med in medications}

        for mid in m_ids:
            m = medication_dict.get(mid)
            if not m: continue

            drug = request.form.get(f'm_drug_{mid}')
            if drug and m.drug_name != drug: m.drug_name = drug; updated_count += 1

            dosage = request.form.get(f'm_dosage_{mid}')
            if dosage is not None and m.dosage != dosage: m.dosage = dosage; updated_count += 1

            amount = request.form.get(f'm_amount_{mid}')
            if amount is not None and m.amount_used != amount: m.amount_used = amount; updated_count += 1

            rem = request.form.get(f'm_rem_{mid}')
            if rem is not None and m.remarks != rem: m.remarks = rem; updated_count += 1

            start = request.form.get(f'm_start_{mid}')
            if start:
                try:
                    d = datetime.strptime(start, '%Y-%m-%d').date()
                    if m.start_date != d: m.start_date = d; updated_count += 1
                except: pass

            end = request.form.get(f'm_end_{mid}')
            if end:
                try:
                    d = datetime.strptime(end, '%Y-%m-%d').date()
                    if m.end_date != d: m.end_date = d; updated_count += 1
                except: pass
            elif end == '' and m.end_date is not None:
                m.end_date = None; updated_count += 1

        if updated_count > 0:
            safe_commit()
            flash(f'Updated {updated_count} records.', 'success')

        flock_id_param = request.form.get('flock_id') or selected_flock_id

        return redirect(url_for('health_log_medication', flock_id=flock_id_param, edit_flock_id=edit_flock_id))

    active_flocks = Flock.query.filter_by(status='Active').options(joinedload(Flock.house)).all()
    for f in active_flocks:
        days = (today - f.intake_date).days
        f.current_week = 0 if days == 0 else ((days - 1) // 7) + 1 if days > 0 else 0

    flock_tasks = {}
    target_flocks = [f for f in active_flocks if str(f.id) == selected_flock_id] if selected_flock_id else active_flocks

    for f in target_flocks:
        flock_tasks[f] = {'medications': Medication.query.filter_by(flock_id=f.id).order_by(Medication.start_date.desc()).all()}

    medication_inventory = InventoryItem.query.filter_by(type='Medication').order_by(InventoryItem.name).all()

    return render_template('health_log_medication.html',
        active_flocks=active_flocks,
        selected_flock_id=int(selected_flock_id) if selected_flock_id else None,
        edit_flock_id=edit_flock_id,
        flock_tasks=flock_tasks,
        medication_inventory=medication_inventory,
        today=today
    )

@app.route('/api/metrics')
def get_metrics_list():
    return json.dumps(METRICS_REGISTRY)

@app.route('/api/flock/<int:flock_id>/custom_data', methods=['POST'])
@login_required
@dept_required('Farm')
def get_custom_data(flock_id):
    flock = Flock.query.get_or_404(flock_id)
    req_data = request.get_json()
    metrics = req_data.get('metrics', [])

    start_date = None
    if req_data.get('start_date'):
        try:
            start_date = datetime.strptime(req_data.get('start_date'), '%Y-%m-%d').date()
        except ValueError: pass

    end_date = None
    if req_data.get('end_date'):
        try:
            end_date = datetime.strptime(req_data.get('end_date'), '%Y-%m-%d').date()
        except ValueError: pass

    logs = DailyLog.query.filter_by(flock_id=flock_id).order_by(DailyLog.date.asc()).all()
    hatchability_data = Hatchability.query.filter_by(flock_id=flock_id).all()

    meds = Medication.query.filter_by(flock_id=flock_id).all()
    vacs = Vaccine.query.filter_by(flock_id=flock_id).filter(Vaccine.actual_date != None).all()

    result = calculate_metrics(logs, flock, metrics, hatchability_data=hatchability_data, start_date=start_date, end_date=end_date)

    result['events'] = []
    for log in logs:
        if start_date and log.date < start_date: continue
        if end_date and log.date > end_date: continue

        # Construct Note
        note_parts = []
        if log.clinical_notes: note_parts.append(log.clinical_notes)
        if log.flushing: note_parts.append("[FLUSHING]")

        # Meds
        active_meds = [m.drug_name for m in meds if m.start_date <= log.date and (m.end_date is None or m.end_date >= log.date)]
        if active_meds: note_parts.append("Meds: " + ", ".join(active_meds))

        # Vacs
        done_vacs = [v.vaccine_name for v in vacs if v.actual_date == log.date]
        if done_vacs: note_parts.append("Vac: " + ", ".join(done_vacs))

        has_photos = len(log.photos) > 0

        if note_parts or has_photos:
             photo_list = []
             for p in log.photos:
                 photo_list.append({
                     'url': url_for('uploaded_file', filename=os.path.basename(p.file_path)),
                     'name': p.original_filename or 'Photo'
                 })

             result['events'].append({
                 'date': log.date.isoformat(),
                 'note': " | ".join(note_parts),
                 'photos': photo_list
             })

    return json.dumps(result)


def get_gemini_response(user_prompt):
    api_key = os.getenv('GEMINI_API_KEY')

    # Check if a custom model is defined, otherwise use the official gemini-1.5-pro model on v1beta
    # Ensure it's not a lite version by avoiding flash models or deprecated versions
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro-latest:generateContent?key={api_key}"

    # System context for the Poultry AI
    context = (
        "You are a Poultry Expert at Sin Long Heng Breeding Farm. "
        "Provide concise advice for Arbor Acres Plus S broiler breeders."
    )

    payload = {
        "contents": [{
            "parts": [{"text": f"{context}\n\nUser Question: {user_prompt}"}]
        }]
    }

    try:
        app.logger.info("Sending request to Gemini AI (gemini-1.5-pro)...")
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status() # Check for errors
        data = response.json()

        # Navigate the JSON structure to get the text
        reply = data['candidates'][0]['content']['parts'][0]['text']
        app.logger.info("Successfully received response from Gemini AI.")
        return reply
    except Exception as e:
        app.logger.error(f"Gemini API Error: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            app.logger.error(f"Gemini API Response: {e.response.text}")
        return f"AI Connection Error: {str(e)}"

@app.route('/api/ai_insight/<int:flock_id>', methods=['GET'])
@login_required
def ai_insight(flock_id):
    flock = Flock.query.get_or_404(flock_id)

    # Needs to be available to both Farm and Executive
    if current_user.role not in ADMIN_FARM_MGMT_ROLES:
        flash('Unauthorized Access.', 'error')
        return redirect(url_for('dashboard'))

    # Get the last 14 days of logs
    recent_logs = DailyLog.query.filter_by(flock_id=flock.id).order_by(DailyLog.date.desc()).limit(14).all()
    # Reverse to process chronologically
    recent_logs.reverse()

    log_data = []
    for log in recent_logs:
        log_entry = {
            "Date": log.date.isoformat(),
            "Mortality (Male)": log.male_dead,
            "Mortality (Female)": log.female_dead,
            "Feed (Male)": log.male_feed,
            "Feed (Female)": log.female_feed,
            "Egg Production (Total)": log.total_eggs,
            "Egg Production (Hatching)": log.hatching_eggs,
            "Water Intake": log.water,
            "Clinical Notes": log.clinical_notes
        }
        # Clean null values
        log_entry = {k: v for k, v in log_entry.items() if v is not None}
        log_data.append(log_entry)

    try:
        global gemini_engine_instance
        if gemini_engine_instance is None:
            # Initialize it dynamically if not created yet to capture env vars
            from gemini_engine import GeminiEngine
            gemini_engine_instance = GeminiEngine()

        ai_response = gemini_engine_instance.analyze_flock_data(
            house_name=flock.house.name if flock.house else "Unknown House",
            log_data=log_data
        )
        return jsonify({"success": True, "insight": ai_response})
    except Exception as e:
        app.logger.error(f"AI Insight Route Error: {str(e)}")
        # Provide the branded error message
        return jsonify({"success": False, "error": "The AI Consultant is currently offline. Please try again in an hour."}), 503

@app.route('/api/chat', methods=['POST'])
@login_required
def chat():
    user_input = request.json.get('message')

    gemini_api_key = os.getenv('GEMINI_API_KEY')

    if gemini_api_key:
        ai_reply = get_gemini_response(user_input)
    else:
        app.logger.warning("Attempted to use AI chat but GEMINI_API_KEY is missing.")
        return jsonify({"response": "The AI assistant is in maintenance mode. Please contact the Technical Director."})

    return jsonify({"response": ai_reply})

# --- Inventory Routes ---

@app.route('/inventory')
@login_required
@dept_required('Farm')
def inventory():
    items = InventoryItem.query.order_by(InventoryItem.name).all()
    transactions = InventoryTransaction.query.order_by(InventoryTransaction.transaction_date.desc(), InventoryTransaction.id.desc()).limit(50).all()

    # Monthly Summary
    today = date.today()
    start_of_month = date(today.year, today.month, 1)

    month_txs = InventoryTransaction.query.filter(InventoryTransaction.transaction_date >= start_of_month).all()

    summary_map = {}
    for t in month_txs:
        if t.inventory_item_id not in summary_map:
            summary_map[t.inventory_item_id] = {'purchase': 0, 'usage': 0, 'waste': 0}

        type_key = t.transaction_type.lower()
        if type_key in summary_map[t.inventory_item_id]:
            summary_map[t.inventory_item_id][type_key] += t.quantity

    summary_list = []
    for item in items:
        s = summary_map.get(item.id, {'purchase': 0, 'usage': 0, 'waste': 0})
        summary_list.append({
            'name': item.name,
            'purchase': round(s['purchase'], 2),
            'usage': round(s['usage'], 2),
            'waste': round(s['waste'], 2)
        })

    return render_template('inventory.html', items=items, transactions=transactions, summary=summary_list, current_month=today.strftime('%B %Y'), today=today)

@app.route('/inventory/add', methods=['POST'])
@login_required
@dept_required('Farm')
def add_inventory_item():
    name = request.form.get('name')
    type_ = request.form.get('type')
    unit = request.form.get('unit')
    stock = float(request.form.get('current_stock') or 0)
    min_stock = float(request.form.get('min_stock_level') or 0)
    doses = int(request.form.get('doses_per_unit') or 0) if type_ == 'Vaccine' else None
    batch = request.form.get('batch_number')
    exp_str = request.form.get('expiry_date')
    exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date() if exp_str else None

    item = InventoryItem(
        name=name, type=type_, unit=unit, current_stock=stock,
        min_stock_level=min_stock, doses_per_unit=doses,
        batch_number=batch, expiry_date=exp_date
    )
    db.session.add(item)
    db.session.flush()

    log_user_activity(current_user.id, 'Add', 'InventoryItem', item.id, details={'name': name, 'type': type_, 'initial_stock': stock})

    safe_commit()

    if stock > 0:
        t = InventoryTransaction(
            inventory_item_id=item.id,
            transaction_type='Purchase',
            quantity=stock,
            transaction_date=date.today(),
            notes='Initial Stock'
        )
        db.session.add(t)
        safe_commit()

    flash(f'Added {name} to inventory.', 'success')
    return redirect(url_for('inventory'))

@app.route('/inventory/transaction', methods=['POST'])
@login_required
@dept_required('Farm')
def inventory_transaction():
    item_id = int(request.form.get('inventory_item_id'))
    type_ = request.form.get('transaction_type')
    qty = float(request.form.get('quantity') or 0)
    date_str = request.form.get('transaction_date')
    date_val = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
    notes = request.form.get('notes')

    if qty <= 0:
        flash('Quantity must be positive.', 'danger')
        return redirect(url_for('inventory'))

    item = InventoryItem.query.get_or_404(item_id)

    if type_ in INV_TX_TYPES_USAGE_WASTE:
        item.current_stock -= qty
    else: # Purchase, Adjustment
        item.current_stock += qty

    if item.current_stock < 0:
        flash(f'Warning: Stock for {item.name} went negative.', 'warning')

    t = InventoryTransaction(
        inventory_item_id=item.id,
        transaction_type=type_,
        quantity=qty,
        transaction_date=date_val,
        notes=notes
    )
    db.session.add(t)
    try:
        db.session.flush()
        log_user_activity(current_user.id, 'Add', 'InventoryTransaction', t.id, details={'item_name': item.name, 'type': type_, 'quantity': qty})
        safe_commit()
        flash('Transaction recorded.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error recording transaction: {str(e)}', 'danger')

    return redirect(url_for('inventory'))

@app.route('/inventory/edit/<int:id>', methods=['POST'])
@login_required
@dept_required('Farm')
def edit_inventory_item(id):
    item = InventoryItem.query.get_or_404(id)

    if request.form.get('delete') == '1':
        item_name = item.name
        log_user_activity(current_user.id, 'Delete', 'InventoryItem', id, details={'name': item_name})
        db.session.delete(item)
        safe_commit()
        flash('Item deleted.', 'info')
        return redirect(url_for('inventory'))

    old_data = {
        'name': item.name,
        'type': item.type,
        'unit': item.unit,
        'min_stock_level': item.min_stock_level,
        'doses_per_unit': item.doses_per_unit,
        'batch_number': item.batch_number,
        'expiry_date': item.expiry_date.strftime('%Y-%m-%d') if item.expiry_date else None
    }

    item.name = request.form.get('name')
    item.type = request.form.get('type')
    item.unit = request.form.get('unit')
    item.min_stock_level = float(request.form.get('min_stock_level') or 0)

    doses = request.form.get('doses_per_unit')
    item.doses_per_unit = int(doses) if doses else None

    item.batch_number = request.form.get('batch_number')

    exp = request.form.get('expiry_date')
    if exp:
        item.expiry_date = datetime.strptime(exp, '%Y-%m-%d').date()
    else:
        item.expiry_date = None

    new_data = {
        'name': item.name,
        'type': item.type,
        'unit': item.unit,
        'min_stock_level': item.min_stock_level,
        'doses_per_unit': item.doses_per_unit,
        'batch_number': item.batch_number,
        'expiry_date': item.expiry_date.strftime('%Y-%m-%d') if item.expiry_date else None
    }

    changes = {k: {'old': old_data[k], 'new': new_data[k]} for k in old_data if old_data[k] != new_data[k]}
    if changes:
        log_user_activity(current_user.id, 'Edit', 'InventoryItem', item.id, details=changes)

    safe_commit()
    flash('Item updated.', 'success')
    return redirect(url_for('inventory'))

@app.route('/inventory/transaction/delete/<int:id>', methods=['POST'])
@login_required
@dept_required('Farm')
def delete_inventory_transaction(id):
    if not current_user.role == 'Admin': return redirect(url_for('index'))

    t = InventoryTransaction.query.get_or_404(id)
    item = InventoryItem.query.get(t.inventory_item_id)
    t_type = t.transaction_type
    t_qty = t.quantity
    item_name = item.name if item else "Unknown"

    log_user_activity(current_user.id, 'Delete', 'InventoryTransaction', id, details={'item_name': item_name, 'type': t_type, 'quantity': t_qty})

    # Revert Stock
    if item:
        if t.transaction_type in INV_TX_TYPES_USAGE_WASTE:
            item.current_stock += t.quantity
        else: # Purchase, Adjustment
            item.current_stock -= t.quantity

    db.session.delete(t)
    safe_commit()
    flash(f"Transaction deleted. Stock reverted.", "info")
    return redirect(url_for('inventory'))

@app.route('/inventory/transaction/edit/<int:id>', methods=['POST'])
@login_required
@dept_required('Farm')
def edit_inventory_transaction(id):
    if not current_user.role == 'Admin': return redirect(url_for('index'))

    t = InventoryTransaction.query.get_or_404(id)
    item = InventoryItem.query.get(t.inventory_item_id)

    old_data = {
        'quantity': t.quantity,
        'transaction_type': t.transaction_type,
        'transaction_date': t.transaction_date.strftime('%Y-%m-%d') if t.transaction_date else None,
        'notes': t.notes
    }

    new_qty = float(request.form.get('quantity') or 0)
    new_date_str = request.form.get('transaction_date')
    new_notes = request.form.get('notes')
    new_type = request.form.get('transaction_type')

    if new_qty <= 0:
        flash("Quantity must be positive.", "danger")
        return redirect(url_for('inventory'))

    if new_type and new_type not in INV_TX_TYPES_ALL:
        flash("Invalid transaction type.", "danger")
        return redirect(url_for('inventory'))

    # Revert Old Effect
    if item:
        if t.transaction_type in INV_TX_TYPES_USAGE_WASTE:
            item.current_stock += t.quantity
        else:
            item.current_stock -= t.quantity

    # Update Transaction
    t.quantity = new_qty
    t.notes = new_notes
    if new_type:
        t.transaction_type = new_type

    if new_date_str:
        try:
            t.transaction_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
        except: pass

    new_data = {
        'quantity': t.quantity,
        'transaction_type': t.transaction_type,
        'transaction_date': t.transaction_date.strftime('%Y-%m-%d') if t.transaction_date else None,
        'notes': t.notes
    }

    changes = {k: {'old': old_data[k], 'new': new_data[k]} for k in old_data if old_data[k] != new_data[k]}
    if changes:
        log_user_activity(current_user.id, 'Edit', 'InventoryTransaction', t.id, details=changes)

    # Apply New Effect
    if item:
        if t.transaction_type in INV_TX_TYPES_USAGE_WASTE:
            item.current_stock -= new_qty
        else:
            item.current_stock += new_qty

    safe_commit()
    flash("Transaction updated.", "success")
    return redirect(url_for('inventory'))


def get_projected_start_of_lay(flock):
    """
    Calculates the projected date when the flock will reach 5% egg production.
    """
    if not flock or not flock.intake_date:
        return None, 0

    # Find standard week where egg prod >= 5%
    target_std = Standard.query.filter(Standard.std_egg_prod >= 5).order_by(Standard.week.asc()).first()

    if not target_std:
        # Default fallback if standard not found (e.g. 24 weeks)
        target_week = 24
    else:
        target_week = target_std.week

    days_to_add = (target_week * 7)
    projected_date = flock.intake_date + timedelta(days=days_to_add)

    days_remaining = (projected_date - date.today()).days

    return projected_date, days_remaining




def get_flock_stock_history_bulk(flocks):
    """
    Returns a dictionary mapping flock_id -> {date -> live_stock (start of day)}.
    Optimized for bulk processing.
    """
    if not flocks: return {}

    flock_ids = [f.id for f in flocks]

    # Fetch all logs in one query
    logs = DailyLog.query.filter(DailyLog.flock_id.in_(flock_ids)).order_by(DailyLog.flock_id, DailyLog.date.asc()).all()

    # Group logs by flock
    logs_by_flock = {}
    for log in logs:
        if log.flock_id not in logs_by_flock:
            logs_by_flock[log.flock_id] = []
        logs_by_flock[log.flock_id].append(log)

    result_map = {}

    for f in flocks:
        f_id = f.id
        stock_map = {}
        cum_loss = 0

        # Get logs for this flock
        f_logs = logs_by_flock.get(f_id, [])

        # Calculate stock history
        for log in f_logs:
            stock_map[log.date] = max(0, (f.intake_male + f.intake_female) - cum_loss)
            cum_loss += (log.mortality_male + log.mortality_female + log.culls_male + log.culls_female)

        # Add "latest" entry
        stock_map['latest'] = max(0, (f.intake_male + f.intake_female) - cum_loss)
        result_map[f_id] = stock_map

    return result_map


def get_weekly_data_aggregated(flocks):
    """
    Aggregates data for the given flocks by ISO Week.
    Returns a dictionary structure:
    {
        '2025-W40': {
            'week_str': '2025-W40',
            'start_date': date_obj,
            'end_date': date_obj,
            'flock_data': {
                flock_id: { ... metrics ... }
            }
        }
    }
    """
    if not flocks:
        return {}

    flock_ids = [f.id for f in flocks]

    # 1. Fetch all Daily Logs
    logs = DailyLog.query.filter(DailyLog.flock_id.in_(flock_ids))\
        .order_by(DailyLog.date.desc()).all()

    # 2. Fetch all Hatchability Data
    hatch_records = Hatchability.query.filter(Hatchability.flock_id.in_(flock_ids))\
        .order_by(Hatchability.setting_date.desc()).all()

    # 3. Fetch Standards
    standards = Standard.query.all()
    std_map = {getattr(s, 'week'): s for s in standards if hasattr(s, 'week')}
    prod_std_map = {getattr(s, 'production_week'): s for s in standards if hasattr(s, 'production_week') and getattr(s, 'production_week')}

    weekly_agg = {}

    # Helper to init week entry
    def init_week(key, start_d, end_d):
        if key not in weekly_agg:
            weekly_agg[key] = {
                'week_str': key,
                'start_date': start_d,
                'end_date': end_d,
                'flock_data': {}
            }
        return weekly_agg[key]

    # Process Logs
    for log in logs:
        # Determine ISO Week
        isocal = log.date.isocalendar() # (Year, Week, Weekday)
        year, week, _ = isocal
        week_key = f"{year}-W{week:02d}"

        # Start/End of that week
        # ISO week starts on Monday
        # Python's isocalendar usage
        monday = log.date - timedelta(days=log.date.weekday())
        sunday = monday + timedelta(days=6)

        entry = init_week(week_key, monday, sunday)

        f_id = log.flock_id
        if f_id not in entry['flock_data']:
            entry['flock_data'][f_id] = {
                'mort_m': 0, 'mort_f': 0,
                'cull_m': 0, 'cull_f': 0,
                'eggs': 0,
                'feed_total_kg': 0,
                'feed_g_bird_sum_f': 0, 'feed_g_bird_count': 0,
                'bw_f_sum': 0, 'bw_f_count': 0,
                'unif_f_sum': 0, 'unif_f_count': 0,
                'stock_f_start': 0, # Need to estimate
                'log_count': 0,
                'logs': [] # Keep references for sparklines if needed
            }

        fd = entry['flock_data'][f_id]
        fd['mort_m'] += (log.mortality_male or 0)
        fd['mort_f'] += (log.mortality_female or 0)
        fd['cull_m'] += (log.culls_male or 0)
        fd['cull_f'] += (log.culls_female or 0)
        fd['eggs'] += (log.eggs_collected or 0)
        # We don't have stock for this day immediately accessible here without calculating it
        # But for 'feed_total_kg' we can just set it to 0 and rely on `enrich_flock_data` for accurate metrics later
        fd['feed_total_kg'] += 0 # Removed explicit reference to log.feed_male

        if log.feed_female_gp_bird > 0:
            fd['feed_g_bird_sum_f'] += log.feed_female_gp_bird
            fd['feed_g_bird_count'] += 1

        if log.body_weight_female > 0:
            fd['bw_f_sum'] += log.body_weight_female
            fd['bw_f_count'] += 1

        if log.uniformity_female > 0:
            fd['unif_f_sum'] += log.uniformity_female
            fd['unif_f_count'] += 1

        fd['log_count'] += 1
        fd['logs'].append(log)

    # Process Hatch Data
    # Link Hatch Data to Week of SETTING or HATCHING?
    # Usually Hatchability is reported on Hatch Date week.
    for h in hatch_records:
        isocal = h.hatching_date.isocalendar()
        year, week, _ = isocal
        week_key = f"{year}-W{week:02d}"

        monday = h.hatching_date - timedelta(days=h.hatching_date.weekday())
        sunday = monday + timedelta(days=6)

        entry = init_week(week_key, monday, sunday)
        f_id = h.flock_id

        if f_id not in entry['flock_data']:
            entry['flock_data'][f_id] = {
                # Init zeros for farm metrics if no logs exist this week
                'mort_m': 0, 'mort_f': 0, 'cull_m': 0, 'cull_f': 0, 'eggs': 0,
                'feed_total_kg': 0, 'feed_g_bird_sum_f': 0, 'feed_g_bird_count': 0,
                'bw_f_sum': 0, 'bw_f_count': 0, 'unif_f_sum': 0, 'unif_f_count': 0,
                'log_count': 0, 'logs': [],
                # Hatch Metrics
                'hatched': 0, 'set': 0
            }

        fd = entry['flock_data'][f_id]
        if 'hatched' not in fd:
            fd['hatched'] = 0
            fd['set'] = 0

        fd['hatched'] += (h.hatched_chicks or 0)
        fd['set'] += (h.egg_set or 0)

    # Calculate Rates and Standard Deviations
    # Need Stock history for Mortality %
    stock_history_bulk = get_flock_stock_history_bulk(flocks)

    flock_objs = {f.id: f for f in flocks}

    # Sort weeks descending
    sorted_weeks = sorted(weekly_agg.keys(), reverse=True)

    final_data = []

    for w_key in sorted_weeks:
        w_data = weekly_agg[w_key]
        row = {
            'week': w_key,
            'start_date': w_data['start_date'],
            'end_date': w_data['end_date'],
            'flocks': []
        }

        for f_id, data in w_data['flock_data'].items():
            flock = flock_objs.get(f_id)
            if not flock: continue

            # Age Calculation (at end of week)
            age_days = (w_data['end_date'] - flock.intake_date).days
            age_week = 0 if age_days == 0 else ((age_days - 1) // 7) + 1 if age_days > 0 else (age_days // 7)
            if age_week < 0: age_week = 0

            # Standards
            std_bio = std_map.get(age_week) # Biological Standard (BW)

            # Production Standard Lookup
            std_prod = None
            if flock.start_of_lay_date:
                start_days = (flock.start_of_lay_date - flock.intake_date).days
                start_bio_week = 0 if start_days == 0 else ((start_days - 1) // 7) + 1 if start_days > 0 else (start_days // 7)
                if age_week >= start_bio_week:
                    current_prod_week = age_week - start_bio_week + 1
                    std_prod = prod_std_map.get(current_prod_week)

            # Stock Calculation
            # Use stock at start of week
            stock_hist = stock_history_bulk.get(f_id, {})
            # Find closest date <= start_date
            start_stock_f = flock.intake_female # Default

            # We can use the stock_history keys.
            # stock_history map has date -> stock at start of that day.
            # So start_stock_f should be stock at w_data['start_date']

            # Use linear search on sorted keys as optimization
            hist_dates = sorted([d for d in stock_hist.keys() if isinstance(d, date)])
            best_date = None
            for d in hist_dates:
                if d <= w_data['start_date']:
                    best_date = d
                else:
                    break

            if best_date:
                start_stock_f = stock_hist[best_date]

            # Calculations
            mort_f_pct = (data['mort_f'] / start_stock_f * 100) if start_stock_f > 0 else 0

            hen_days = start_stock_f * 7 # Approximate
            # Precise hen days = sum daily stock?
            # If we have logs, we can sum daily stock.
            # But we aggregated logs manually.
            # Let's use simple approximation for Executive view speed.

            egg_prod_pct = (data['eggs'] / hen_days * 100) if hen_days > 0 else 0

            hatch_pct = (data.get('hatched', 0) / data.get('set', 0) * 100) if data.get('set', 0) > 0 else 0

            avg_bw_f = (data['bw_f_sum'] / data['bw_f_count']) if data['bw_f_count'] > 0 else 0
            avg_unif_f = (data['unif_f_sum'] / data['unif_f_count']) if data['unif_f_count'] > 0 else 0
            avg_feed_f = (data['feed_g_bird_sum_f'] / data['feed_g_bird_count']) if data['feed_g_bird_count'] > 0 else 0

            # Generate Sparkline Data (Daily within this week)
            # data['logs'] contains daily logs.
            # We need to sort them.
            daily_logs = sorted(data['logs'], key=lambda x: x.date)
            spark_bw = [l.body_weight_female for l in daily_logs if l.body_weight_female > 0]
            spark_eggs = [((l.eggs_collected or 0)/(start_stock_f or 1)*100) for l in daily_logs] # Approx %

            # Feed Code (Take last used)
            feed_code = "N/A"
            if daily_logs:
                last_log = daily_logs[-1]
                if last_log.feed_code_female:
                    feed_code = last_log.feed_code_female.code
                elif last_log.feed_code_male:
                    feed_code = last_log.feed_code_male.code

            flock_metrics = {
                'flock_obj': flock,
                'age_week': age_week,
                'total_eggs': data['eggs'],
                'mort_f_pct': round(mort_f_pct, 2),
                'egg_prod_pct': round(egg_prod_pct, 2),
                'hatch_pct': round(hatch_pct, 2),
                'avg_bw_f': int(avg_bw_f),
                'avg_unif_f': round(avg_unif_f, 1),
                'avg_feed_f': int(avg_feed_f),
                'feed_code': feed_code,
                'std_bw_f': std_bio.std_bw_female if std_bio else None,
                'std_egg_prod': std_prod.std_egg_prod if std_prod else None,
                'spark_bw': spark_bw,
                'spark_eggs': spark_eggs
            }

            row['flocks'].append(flock_metrics)

        final_data.append(row)

    return final_data



import math

def calculate_grading_stats(weights):
    if not weights:
        return None

    count = len(weights)
    avg_weight = sum(weights) / count
    lower_limit = avg_weight * 0.9
    upper_limit = avg_weight * 1.1

    in_range = sum(1 for w in weights if lower_limit <= w <= upper_limit)
    uniformity = (in_range / count) * 100 if count > 0 else 0.0

    lowest = min(weights)
    highest = max(weights)

    # Bins: Floor lowest to 100, ceil highest to 100
    bin_min = int(math.floor(lowest / 100.0)) * 100
    bin_max = int(math.ceil(highest / 100.0)) * 100

    # Initialize bins with zero counts to ensure they're ordered
    bins = {}
    for b in range(bin_min, bin_max + 100, 100):
        bins[str(b)] = 0

    # Populate bins
    for w in weights:
        # Find which bin it belongs to
        # Normally, a bin like 1500 means [1450, 1550) or [1500, 1600)?
        # Looking at standard distributions, usually round to nearest 100
        # If w = 1530, round(1530/100)*100 = 1500. Let's use standard rounding.
        b_key = str(int(round(w / 100.0)) * 100)
        if b_key in bins:
            bins[b_key] += 1
        else:
            # Fallback if outside somehow
            bins[b_key] = 1

    return {
        'count': count,
        'average_weight': round(avg_weight, 2),
        'uniformity': round(uniformity, 2),
        'lowest_weight': lowest,
        'highest_weight': highest,
        'grading_bins': json.dumps(bins)
    }

@app.route('/upload_weights', methods=['POST'])
@login_required
@dept_required(['Farm', 'Management'])
def upload_weights():
    house_id = request.form.get('house_id')
    age_week = request.form.get('age_week')

    if not house_id or not age_week:
        flash("House and Age Week are required.", "danger")
        return redirect(url_for('health_log_bodyweight'))

    if 'file' not in request.files:
        flash("No file part.", "danger")
        return redirect(url_for('weight_grading'))

    file = request.files['file']
    if file.filename == '':
        flash("No selected file.", "danger")
        return redirect(url_for('weight_grading'))

    if file and (file.filename.endswith('.csv') or file.filename.endswith('.xlsx')):



        try:
            if file.filename.endswith('.csv'):
                df_dict = {'Sheet1': pd.read_csv(file, header=None)}
            else:
                df_dict = pd.read_excel(file, sheet_name=None, header=None)

            m_weights = []
            f_weights = []

            for sheet_name, df in df_dict.items():
                active_sex = None
                collecting = False

                for index in range(len(df)):
                    row = df.iloc[index]

                    # 1. The Scanner Phase (Column B is index 1)
                    if len(row) > 1 and pd.notna(row[1]):
                        col_b_val = str(row[1]).strip()
                        if col_b_val:
                            # Use regex to find (M|F)
                            match = re.search(r'\b(M|F)\b', col_b_val.upper())
                            if match:
                                active_sex = 'Male' if match.group(1) == 'M' else 'Female'
                                collecting = False # Stop collecting previous block

                    # 2. The Data Trigger (Column D is index 3)
                    if len(row) > 3 and pd.notna(row[3]):
                        col_d_val = str(row[3]).strip()

                        if active_sex and 'weight [g]' in col_d_val.lower():
                            collecting = True
                            continue # Skip the header row itself

                        # 3. The Aggregation Phase
                        if collecting:
                            try:
                                w = float(col_d_val)
                                if pd.isna(w) or w <= 0:
                                    continue

                                if active_sex == 'Male':
                                    m_weights.append(w)
                                elif active_sex == 'Female':
                                    f_weights.append(w)
                            except ValueError:
                                # Stop collecting on non-numeric value (like footer or new header)
                                collecting = False
                    else:
                        # Stop collecting if Column D is empty
                        collecting = False

            # Process and save


            if m_weights:

                stats = calculate_grading_stats(m_weights)
                if stats:
                    # Check if exists
                    grading = FlockGrading.query.filter_by(house_id=house_id, age_week=age_week, sex='Male').first()
                    if not grading:
                        grading = FlockGrading(house_id=house_id, age_week=age_week, sex='Male')
                        db.session.add(grading)

                    grading.count = stats['count']
                    grading.average_weight = stats['average_weight']
                    grading.uniformity = stats['uniformity']
                    grading.lowest_weight = stats['lowest_weight']
                    grading.highest_weight = stats['highest_weight']
                    grading.grading_bins = stats['grading_bins']

            if f_weights:
                stats = calculate_grading_stats(f_weights)
                if stats:
                    # Check if exists
                    grading = FlockGrading.query.filter_by(house_id=house_id, age_week=age_week, sex='Female').first()
                    if not grading:
                        grading = FlockGrading(house_id=house_id, age_week=age_week, sex='Female')
                        db.session.add(grading)

                    grading.count = stats['count']
                    grading.average_weight = stats['average_weight']
                    grading.uniformity = stats['uniformity']
                    grading.lowest_weight = stats['lowest_weight']
                    grading.highest_weight = stats['highest_weight']
                    grading.grading_bins = stats['grading_bins']

            safe_commit()

            # Unconditional Push Alert
            try:
                house = House.query.get(house_id)
                house_name = house.name if house else "Unknown House"
                title = "SLH-OP: Grading Report"
                body = f"{house_name}: Week {age_week} Selection/Grading Report is now available."
                # We don't have flock id directly, but we can redirect to bodyweight page
                alert_url = url_for('health_log_bodyweight')

                all_users = User.query.all()
                for user in all_users:
                    send_push_alert(user.id, title, body, url=alert_url)
            except Exception as e:
                app.logger.error(f"Failed to send Grading Report push alert: {str(e)}")

            flash(f"Successfully processed weights. Males: {len(m_weights)}, Females: {len(f_weights)}", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error processing file: {str(e)}", "danger")
    else:
        flash("Invalid file format. Please upload .csv or .xlsx", "danger")

    return redirect(url_for('health_log_bodyweight'))

@app.route('/health_log/bodyweight', methods=['GET', 'POST'])
@login_required
@dept_required(['Farm', 'Management', 'Admin'])
def health_log_bodyweight():
    if request.method == 'POST':
        flock_id = request.form.get('flock_id')
        date_str = request.form.get('date')

        if not flock_id or not date_str:
            flash("House and Date are required.", "danger")
            return redirect(url_for('health_log_bodyweight'))

        try:
            log_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            flash("Invalid date format.", "danger")
            return redirect(url_for('weight_grading'))

        log = DailyLog.query.filter_by(flock_id=flock_id, date=log_date).first()
        if not log:
            log = DailyLog(
                flock_id=flock_id,
                date=log_date,                body_weight_male=0,
                body_weight_female=0
            )
            db.session.add(log)
            db.session.flush()

        log.is_weighing_day = True

        # Male weights
        if request.form.get('body_weight_male'):
            log.body_weight_male = float(request.form.get('body_weight_male'))
        if request.form.get('uniformity_male'):
            val = float(request.form.get('uniformity_male'))
            log.uniformity_male = val if val > 1.0 else (val * 100)
        if request.form.get('standard_bw_male'):
            log.standard_bw_male = round_to_whole(request.form.get('standard_bw_male'))

        # Female weights
        if request.form.get('body_weight_female'):
            log.body_weight_female = float(request.form.get('body_weight_female'))
        if request.form.get('uniformity_female'):
            val = float(request.form.get('uniformity_female'))
            log.uniformity_female = val if val > 1.0 else (val * 100)
        if request.form.get('standard_bw_female'):
            log.standard_bw_female = round_to_whole(request.form.get('standard_bw_female'))

        # Save Partitions
        existing_partitions = {pw.partition_name: pw for pw in log.partition_weights}

        def save_partition(name, bw_str, unif_str):
            bw = float(bw_str) if bw_str else 0
            unif = float(unif_str) if unif_str else 0
            unif = unif if unif > 1.0 else (unif * 100) if unif > 0 else 0
            if bw > 0:
                if name in existing_partitions:
                    existing_partitions[name].body_weight = bw
                    existing_partitions[name].uniformity = unif
                else:
                    pw = PartitionWeight(log_id=log.id, partition_name=name, body_weight=bw, uniformity=unif)
                    db.session.add(pw)
            elif name in existing_partitions:
                db.session.delete(existing_partitions[name])

        for i in range(1, 9):
            save_partition(f'M{i}', request.form.get(f'bw_M{i}'), request.form.get(f'uni_M{i}'))
            save_partition(f'F{i}', request.form.get(f'bw_F{i}'), request.form.get(f'uni_F{i}'))

        safe_commit()

        # Unconditional Push Alert
        try:
            house_name = log.flock.house.name if log.flock and log.flock.house else "Unknown House"
            age_week = 0
            if log.flock and log.flock.intake_date:
                age_week = (log.date - log.flock.intake_date).days // 7

            title = "SLH-OP: Weight Entry"
            body = f"{house_name}: Week {age_week} Bodyweight updated."
            alert_url = url_for('health_log_bodyweight')

            all_users = User.query.all()
            for user in all_users:
                send_push_alert(user.id, title, body, url=alert_url)
        except Exception as e:
            app.logger.error(f"Failed to send Bodyweight push alert: {str(e)}")

        flash("Bodyweight data saved successfully.", "success")
        return redirect(url_for('health_log_bodyweight'))

    if current_user.role == 'Admin':
        active_flocks = Flock.query.filter_by(status='Active').options(joinedload(Flock.house)).all()
    else:
        active_flocks = Flock.query.filter_by(status='Active', farm_id=current_user.farm_id).options(joinedload(Flock.house)).all()


    if active_flocks:
            active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else ''))

    # Fetch all records, sort by house name, then age week descending
    records = db.session.query(FlockGrading, House.name).join(House).order_by(House.name, FlockGrading.age_week.desc()).all()

    # Group by House -> Week -> Sex
    # Result format: { 'House A': { 13: { 'Male': grading_obj, 'Female': grading_obj } } }
    grouped_data = {}
    for grading, house_name in records:
        if house_name not in grouped_data:
            grouped_data[house_name] = {}
        if grading.age_week not in grouped_data[house_name]:
            grouped_data[house_name][grading.age_week] = {}
        grouped_data[house_name][grading.age_week][grading.sex] = grading

    houses = House.query.order_by(House.name).all()

    # active_flocks is already fetched and sorted above

    # Fetch bodyweight logs (is_weighing_day=True)
    logs = DailyLog.query.join(Flock).join(House).options(
        joinedload(DailyLog.partition_weights),
        joinedload(DailyLog.flock).joinedload(Flock.house)
    ).filter(DailyLog.is_weighing_day == True).order_by(DailyLog.date.desc()).all()

    # We also need grading reports to know if "Selection Report" is available
    reports = FlockGrading.query.all()
    reports_map = {}
    for r in reports:
        key = (r.house_id, r.age_week)
        reports_map[key] = True

    # Group logs by house to calculate prev week diffs
    logs_by_house = {}
    for log in logs:
        hid = log.flock.house_id
        if hid not in logs_by_house:
            logs_by_house[hid] = []
        logs_by_house[hid].append(log)

    bodyweight_logs = []

    for log in logs:
        age_days = (log.date - log.flock.intake_date).days
        age_weeks = age_days // 7

        house_logs = logs_by_house[log.flock.house_id]

        prev_log = None
        for hl in house_logs:
            hl_age_weeks = (hl.date - hl.flock.intake_date).days // 7
            if hl_age_weeks == age_weeks - 1:
                prev_log = hl
                break

        def get_p(l, name):
            if not l: return None
            for pw in l.partition_weights:
                if pw.partition_name == name:
                    return pw
            return None

        m_parts = []
        f_parts = []

        std_m = log.standard_bw_male
        std_f = log.standard_bw_female

        # Fallback to Standard model if not saved in log or is 0
        if not std_m or not std_f:
            std_record = Standard.query.filter_by(week=age_weeks).first()
            if std_record:
                if not std_m: std_m = std_record.std_bw_male
                if not std_f: std_f = std_record.std_bw_female

        avg_m_diff = "N/A"
        if prev_log and log.body_weight_male is not None and prev_log.body_weight_male is not None:
            diff = log.body_weight_male - prev_log.body_weight_male
            avg_m_diff = f"{'+' if diff > 0 else ''}{diff:.0f}g"

        avg_f_diff = "N/A"
        if prev_log and log.body_weight_female is not None and prev_log.body_weight_female is not None:
            diff = log.body_weight_female - prev_log.body_weight_female
            avg_f_diff = f"{'+' if diff > 0 else ''}{diff:.0f}g"

        for i in range(1, 9):
            cur_m = get_p(log, f'M{i}')
            if cur_m and cur_m.body_weight > 0:
                prev_m = get_p(prev_log, f'M{i}')
                diff_g = "N/A"
                diff_u = "N/A"
                if prev_m and prev_m.body_weight > 0:
                    dg = cur_m.body_weight - prev_m.body_weight
                    diff_g = f"{'+' if dg > 0 else ''}{dg:.0f}g"
                    du = cur_m.uniformity - prev_m.uniformity
                    diff_u = f"{'+' if du > 0 else ''}{du:.1f}%"

                var_pct = 0
                if std_m and std_m > 0:
                    var_pct = ((cur_m.body_weight - std_m) / std_m) * 100

                m_parts.append({
                    'name': f'P{i}',
                    'bw': cur_m.body_weight,
                    'unif': cur_m.uniformity,
                    'diff_g': diff_g,
                    'diff_u': diff_u,
                    'var_pct': var_pct
                })

            cur_f = get_p(log, f'F{i}')
            if cur_f and cur_f.body_weight > 0:
                prev_f = get_p(prev_log, f'F{i}')
                diff_g = "N/A"
                diff_u = "N/A"
                if prev_f and prev_f.body_weight > 0:
                    dg = cur_f.body_weight - prev_f.body_weight
                    diff_g = f"{'+' if dg > 0 else ''}{dg:.0f}g"
                    du = cur_f.uniformity - prev_f.uniformity
                    diff_u = f"{'+' if du > 0 else ''}{du:.1f}%"

                var_pct = 0
                if std_f and std_f > 0:
                    var_pct = ((cur_f.body_weight - std_f) / std_f) * 100

                f_parts.append({
                    'name': f'P{i}',
                    'bw': cur_f.body_weight,
                    'unif': cur_f.uniformity,
                    'diff_g': diff_g,
                    'diff_u': diff_u,
                    'var_pct': var_pct
                })

        has_report = reports_map.get((log.flock.house_id, age_weeks), False)

        avg_m_var = 0
        if log.body_weight_male and std_m:
            avg_m_var = ((log.body_weight_male - std_m) / std_m) * 100
        avg_f_var = 0
        if log.body_weight_female and std_f:
            avg_f_var = ((log.body_weight_female - std_f) / std_f) * 100

        bodyweight_logs.append({
            'log_id': log.id,
            'house_name': log.flock.house.name,
            'house_id': log.flock.house_id,
            'age_weeks': age_weeks,
            'date': log.date.strftime('%Y-%m-%d'),
            'std_m': std_m or 0,
            'std_f': std_f or 0,
            'avg_m': log.body_weight_male or 0,
            'avg_f': log.body_weight_female or 0,
            'avg_m_diff': avg_m_diff,
            'avg_f_diff': avg_f_diff,
            'avg_m_var': avg_m_var,
            'avg_f_var': avg_f_var,
            'm_parts': m_parts,
            'f_parts': f_parts,
            'has_report': has_report,
            'uni_m': (log.uniformity_male * 100) if (log.uniformity_male and log.uniformity_male <= 1.0) else (log.uniformity_male or 0),
            'uni_f': (log.uniformity_female * 100) if (log.uniformity_female and log.uniformity_female <= 1.0) else (log.uniformity_female or 0)
        })

    return render_template('bodyweight.html', houses=houses, active_flocks=active_flocks, bodyweight_logs=bodyweight_logs, grouped_data=grouped_data, today=date.today())


@app.route('/api/health_log/bodyweight_edit', methods=['POST'])
@login_required
@dept_required(['Farm', 'Management', 'Admin'])
def health_log_bodyweight_edit():
    log_id = request.form.get('log_id', type=int)
    new_date_str = request.form.get('new_date')

    if not log_id or not new_date_str:
        return jsonify({"success": False, "message": "Log ID and Date are required."}), 400

    try:
        new_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({"success": False, "message": "Invalid date format."}), 400

    # Get original log
    orig_log = DailyLog.query.get(log_id)
    if not orig_log:
        return jsonify({"success": False, "message": "Original log not found."}), 404

    flock_id = orig_log.flock_id

    # Check if target log exists for the new date
    target_log = DailyLog.query.filter_by(flock_id=flock_id, date=new_date).first()

    if not target_log:
        target_log = DailyLog(
            flock_id=flock_id,
            date=new_date,            body_weight_male=0,
            body_weight_female=0
        )
        db.session.add(target_log)
        db.session.flush()

    target_log.is_weighing_day = True

    # If moving to a different date, clear original log's weight data
    if orig_log.id != target_log.id:
        # Transfer the standard bodyweight thresholds
        target_log.standard_bw_male = orig_log.standard_bw_male
        target_log.standard_bw_female = orig_log.standard_bw_female

        orig_log.is_weighing_day = False
        orig_log.body_weight_male = 0
        orig_log.body_weight_female = 0
        orig_log.uniformity_male = 0
        orig_log.uniformity_female = 0
        orig_log.standard_bw_male = None
        orig_log.standard_bw_female = None

        # Delete old partitions from original log
        PartitionWeight.query.filter_by(log_id=orig_log.id).delete()

    # Parse new weights and update target log
    m_avg = request.form.get('avg_m', type=float) or 0.0
    f_avg = request.form.get('avg_f', type=float) or 0.0
    m_uni = request.form.get('uni_m', type=float) or 0.0
    f_uni = request.form.get('uni_f', type=float) or 0.0

    target_log.body_weight_male = m_avg
    target_log.body_weight_female = f_avg

    # Handle uniformity format
    target_log.uniformity_male = m_uni if m_uni > 1.0 else (m_uni * 100) if m_uni > 0 else 0
    target_log.uniformity_female = f_uni if f_uni > 1.0 else (f_uni * 100) if f_uni > 0 else 0

    # We do not change standard_bw_male/female as it's typically set by the standard
    # But if the user also submitted standard weights, we can update them
    # target_log.standard_bw_male = orig_log.standard_bw_male (this logic is complex, keeping it as is or recalculating based on standard model)

    # Process partitions
    existing_partitions = {pw.partition_name: pw for pw in target_log.partition_weights}
    new_partition_names = []

    # Iterate through possible partitions M1-M8, F1-F8
    for sex in ['M', 'F']:
        for i in range(1, 9):
            p_name = f"{sex}{i}"
            bw_str = request.form.get(f'bw_{p_name}')
            unif_str = request.form.get(f'uni_{p_name}')

            bw = float(bw_str) if bw_str else 0
            unif = float(unif_str) if unif_str else 0
            unif = unif if unif > 1.0 else (unif * 100) if unif > 0 else 0

            if bw > 0:
                new_partition_names.append(p_name)
                if p_name in existing_partitions:
                    existing_partitions[p_name].body_weight = bw
                    existing_partitions[p_name].uniformity = unif
                else:
                    pw = PartitionWeight(log_id=target_log.id, partition_name=p_name, body_weight=bw, uniformity=unif)
                    db.session.add(pw)

    # Remove partitions that are no longer present
    for name, pw in existing_partitions.items():
        if name not in new_partition_names:
            db.session.delete(pw)

    safe_commit()
    return jsonify({"success": True, "message": "Bodyweight updated successfully."}), 200


@app.route('/additional_report')
@login_required
def additional_report():
    # Role Check: Admin or Management
    if not current_user.role == 'Admin' and current_user.role != 'Management':
        flash("Access Denied: Executive View Only.", "danger")
        return redirect(url_for('index'))

    # Active Flocks
    active_flocks = Flock.query.filter_by(status='Active').options(joinedload(Flock.house)).all()

    if active_flocks:
            active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else ''))

    prod_flocks = [f for f in active_flocks if f.phase == 'Production']
    rearing_flocks = [f for f in active_flocks if f.phase == 'Rearing']

    # Get Aggregated Data
    # We fetch ALL data in one go or per group? One go is fine, then filter in template or here.
    # Actually, the table structure differs.

    prod_data_weekly = get_weekly_data_aggregated(prod_flocks)
    rearing_data_weekly = get_weekly_data_aggregated(rearing_flocks)

    # Countdown Logic for Rearing Flocks
    countdowns = []
    for f in rearing_flocks:
        p_date, d_rem = get_projected_start_of_lay(f)
        countdowns.append({
            'flock': f,
            'projected_date': p_date,
            'days_remaining': d_rem
        })

    # Leaderboard (Active Flocks)
    # Top House (Best Egg Prod % - Current Week?)
    # Let's use the most recent week in prod_data_weekly
    top_house = None
    best_prod = -1

    top_hatch_batch = None
    best_hatch = -1

    # Iterate latest week of production data
    if prod_data_weekly:
        latest_week = prod_data_weekly[0] # Sorted descending
        for f_metric in latest_week['flocks']:
            # Egg Prod
            if f_metric['egg_prod_pct'] > best_prod:
                best_prod = f_metric['egg_prod_pct']
                top_house = f_metric['flock_obj'].house.name

            # Hatch
            if f_metric['hatch_pct'] > best_hatch:
                best_hatch = f_metric['hatch_pct']
                top_hatch_batch = f_metric['flock_obj'].flock_id

    leaderboard = {
        'top_house': top_house,
        'best_prod': best_prod,
        'top_hatch_batch': top_hatch_batch,
        'best_hatch': best_hatch
    }

    # Inventory Usage (Monthly) - Same as before
    usage_txs = InventoryTransaction.query.options(joinedload(InventoryTransaction.item)).filter(
        InventoryTransaction.transaction_type == 'Usage'
    ).order_by(InventoryTransaction.transaction_date.desc()).all()

    inventory_usage = {}
    for tx in usage_txs:
        month_str = tx.transaction_date.strftime('%Y-%m')
        key = (month_str, tx.item.name, tx.item.unit)
        if key not in inventory_usage: inventory_usage[key] = 0.0
        inventory_usage[key] += tx.quantity

    usage_list = []
    for (month, name, unit), qty in inventory_usage.items():
        usage_list.append({'month': month, 'name': name, 'unit': unit, 'qty': qty})

    usage_list.sort(key=lambda x: x['month'], reverse=True)

    # Date Header
    today = date.today()
    current_month_name = today.strftime('%B %Y')
    isocal = today.isocalendar()
    current_iso_week = f"{isocal[0]}-W{isocal[1]:02d}"

    return render_template('additional_report.html',
                           prod_data=prod_data_weekly,
                           rearing_data=rearing_data_weekly,
                           countdowns=countdowns,
                           leaderboard=leaderboard,
                           inventory_usage=usage_list,
                           current_month=current_month_name,
                           current_iso_week=current_iso_week)

def get_iso_aggregated_data_sql(flock_ids, target_year):
    """
    Aggregates data by ISO week using raw SQL for performance.
    Handles stock calculation (Intake - Cumulative Loss) dynamically.
    Returns:
    {
        'weekly': [...],
        'monthly': [...],
        'yearly': [...]
    }
    """
    if not flock_ids:
        return {'weekly': [], 'monthly': [], 'yearly': []}

    ids_tuple = tuple(flock_ids)
    if len(ids_tuple) == 1:
        ids_tuple = f"({ids_tuple[0]})"
    else:
        ids_tuple = str(ids_tuple)

    # Common CTE for calculating daily metrics
    # Determine the database dialect
    dialect = db.engine.name

    if dialect == 'sqlite':
        week_fmt = "strftime('%Y-%W', l.date)"
        month_fmt = "strftime('%Y-%m', l.date)"
        year_fmt = "strftime('%Y', l.date)"
    else:  # postgresql
        week_fmt = "to_char(l.date, 'IYYY-IW')"
        month_fmt = "to_char(l.date, 'YYYY-MM')"
        year_fmt = "to_char(l.date, 'YYYY')"

    cte_sql = f"""
    WITH DailyStock AS (
        SELECT
            l.date,
            l.flock_id,
            {week_fmt} as iso_week,
            {month_fmt} as iso_month,
            {year_fmt} as iso_year,
            l.mortality_male + l.mortality_female + l.culls_male + l.culls_female as daily_loss,
            l.mortality_female as mort_f,
            l.eggs_collected,
            0 as total_feed,
            f.intake_female + f.intake_male as intake_total,
            f.intake_female,
            f.start_of_lay_date,
            SUM(l.mortality_male + l.mortality_female + l.culls_male + l.culls_female)
                OVER (PARTITION BY l.flock_id ORDER BY l.date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) as cum_loss,
            SUM(l.mortality_female + l.culls_female)
                OVER (PARTITION BY l.flock_id ORDER BY l.date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) as cum_loss_f
        FROM daily_log l
        JOIN flock f ON l.flock_id = f.id
        WHERE l.flock_id IN {ids_tuple}
    ),
    EnrichedDaily AS (
        SELECT
            *,
            (intake_female - cum_loss_f) as stock_f_end,
            -- Stock Start of Day is End of Prev Day (approx by adding back daily loss? No, simpler: Intake - (Cum - Daily))
            (intake_female - (cum_loss_f - (mort_f + 0))) as stock_f_start
        FROM DailyStock
    )
    """

    results = {}

    # Define aggregation queries with UNION ALL to reduce db calls from 6 to 2
    # Filter by Year AND Start of Lay in the Final Step to allow cum_loss to be accurate
    combined_cte_sql = f"""
        {cte_sql},
        WeeklyLogs AS (
            SELECT
                'weekly' as type,
                iso_week as period,
                SUM(eggs_collected) as total_eggs,
                SUM(mort_f) as total_mort_f,
                SUM(stock_f_start) as total_hen_days,
                COUNT(DISTINCT date) as days_in_period
            FROM EnrichedDaily
            WHERE iso_year = :year
              AND start_of_lay_date IS NOT NULL
              AND date >= start_of_lay_date
            GROUP BY iso_week
        ),
        MonthlyLogs AS (
            SELECT
                'monthly' as type,
                iso_month as period,
                SUM(eggs_collected) as total_eggs,
                SUM(mort_f) as total_mort_f,
                SUM(stock_f_start) as total_hen_days,
                COUNT(DISTINCT date) as days_in_period
            FROM EnrichedDaily
            WHERE iso_year = :year
              AND start_of_lay_date IS NOT NULL
              AND date >= start_of_lay_date
            GROUP BY iso_month
        ),
        YearlyLogs AS (
            SELECT
                'yearly' as type,
                iso_year as period,
                SUM(eggs_collected) as total_eggs,
                SUM(mort_f) as total_mort_f,
                SUM(stock_f_start) as total_hen_days,
                COUNT(DISTINCT date) as days_in_period
            FROM EnrichedDaily
            WHERE iso_year = :year
              AND start_of_lay_date IS NOT NULL
              AND date >= start_of_lay_date
            GROUP BY iso_year
        )
        SELECT * FROM WeeklyLogs
        UNION ALL
        SELECT * FROM MonthlyLogs
        UNION ALL
        SELECT * FROM YearlyLogs
    """

    # Define Hatchery Queries based on dialect
    if dialect == 'sqlite':
        hatch_week_fmt = "strftime('%Y-%W', hatching_date)"
        hatch_month_fmt = "strftime('%Y-%m', hatching_date)"
        hatch_year_fmt = "strftime('%Y', hatching_date)"
    else: # postgresql
        hatch_week_fmt = "to_char(hatching_date, 'IYYY-IW')"
        hatch_month_fmt = "to_char(hatching_date, 'YYYY-MM')"
        hatch_year_fmt = "to_char(hatching_date, 'YYYY')"

    combined_hatch_sql = f"""
        WITH WeeklyHatch AS (
            SELECT
                'weekly' as type,
                {hatch_week_fmt} as period,
                SUM(hatched_chicks) as hatched,
                SUM(egg_set) as egg_set
            FROM hatchability
            WHERE flock_id IN {ids_tuple} AND {hatch_year_fmt} = :year
            GROUP BY period
        ),
        MonthlyHatch AS (
            SELECT
                'monthly' as type,
                {hatch_month_fmt} as period,
                SUM(hatched_chicks) as hatched,
                SUM(egg_set) as egg_set
            FROM hatchability
            WHERE flock_id IN {ids_tuple} AND {hatch_year_fmt} = :year
            GROUP BY period
        ),
        YearlyHatch AS (
            SELECT
                'yearly' as type,
                {hatch_year_fmt} as period,
                SUM(hatched_chicks) as hatched,
                SUM(egg_set) as egg_set
            FROM hatchability
            WHERE flock_id IN {ids_tuple} AND {hatch_year_fmt} = :year
            GROUP BY period
        )
        SELECT * FROM WeeklyHatch
        UNION ALL
        SELECT * FROM MonthlyHatch
        UNION ALL
        SELECT * FROM YearlyHatch
    """

    # Fetch all data at once to avoid multiple db calls
    all_logs = db.session.execute(text(combined_cte_sql), {'year': str(target_year)}).fetchall()
    all_hatch = db.session.execute(text(combined_hatch_sql), {'year': str(target_year)}).fetchall()

    # Process results into typed dictionaries
    hatch_map = {'weekly': {}, 'monthly': {}, 'yearly': {}}
    for row in all_hatch:
        # Expected tuple: (type, period, hatched, egg_set)
        type_key = row[0]
        period = row[1]
        hatched = row[2]
        egg_set = row[3]
        if period:
            hatch_map[type_key][period] = (hatched, egg_set)

    logs_by_type = {'weekly': [], 'monthly': [], 'yearly': []}
    for row in all_logs:
        # Expected tuple: (type, period, total_eggs, total_mort_f, total_hen_days, days_in_period)
        type_key = row[0]
        period = row[1]
        if period:
            logs_by_type[type_key].append({
                'period': period,
                'total_eggs': row[2] or 0,
                'total_mort_f': row[3] or 0,
                'total_hen_days': row[4] or 0,
                'days_in_period': row[5] or 0
            })

    for key in ['weekly', 'monthly', 'yearly']:
        # The frontend expects periods to be descending ordered, which is not guaranteed by UNION ALL
        sorted_logs = sorted(logs_by_type[key], key=lambda x: x['period'], reverse=True)

        processed_list = []
        for log in sorted_logs:
            period = log['period']
            total_eggs = log['total_eggs']
            total_mort = log['total_mort_f']
            total_hen_days = log['total_hen_days']
            days_in_period = log['days_in_period']

            # Hatchery
            h_data = hatch_map[key].get(period)
            hatched = h_data[0] if h_data else 0
            set_cnt = h_data[1] if h_data else 0

            # Avg Prod Females = Total Hen Days / Days in Period
            # This represents the average number of birds present on any given day in the period
            avg_stock = (total_hen_days / days_in_period) if days_in_period > 0 else 0

            # Metrics
            mort_pct = (total_mort / avg_stock * 100) if avg_stock > 0 else 0

            # Egg Prod % = Total Eggs / Total Hen Days * 100
            egg_prod_pct = (total_eggs / total_hen_days * 100) if total_hen_days > 0 else 0

            hatch_pct = (hatched / set_cnt * 100) if set_cnt > 0 else 0

            processed_list.append({
                'period': period,
                'avg_prod_females': int(avg_stock), # Renamed for clarity in template usage, but legacy template uses avg_female_stock
                'avg_female_stock': int(avg_stock), # Legacy support
                'total_eggs': total_eggs,
                'total_chicks': hatched,
                'mortality_pct': round(mort_pct, 2),
                'hatchability_pct': round(hatch_pct, 2),
                'overall_egg_prod_pct': round(egg_prod_pct, 2), # Explicit Key
                'egg_production_pct': round(egg_prod_pct, 2) # Legacy Key
            })

        results[key] = processed_list

    return results

def get_iso_aggregated_data(flocks, target_year=None):
    """
    Aggregates data across all given flocks into Weekly, Monthly, and Yearly ISO buckets.
    Returns:
    {
        'weekly': [{period, avg_female_stock, total_eggs, total_chicks, mortality_pct, hatchability_pct, egg_prod_pct}, ...],
        'monthly': [...],
        'yearly': [...]
    }
    """
    if not flocks:
        return {'weekly': [], 'monthly': [], 'yearly': []}

    global_daily = {}

    # Default to current year if None, or handle differently?
    # Requirement: Filter by year.
    filter_year = target_year if target_year else date.today().year

    # Optimization: Bulk fetch Logs and Hatchability to avoid N+1 queries
    flock_ids = [f.id for f in flocks]

    # 1. Bulk Fetch Hatchability
    all_hatch_records = Hatchability.query.filter(Hatchability.flock_id.in_(flock_ids)).all()
    hatch_by_flock = {}
    for h in all_hatch_records:
        if h.flock_id not in hatch_by_flock:
            hatch_by_flock[h.flock_id] = []
        hatch_by_flock[h.flock_id].append(h)

    # 2. Bulk Fetch Logs (Optimized to use existing relationships if available)
    logs_by_flock = {}

    # Check if flocks already have logs loaded (e.g. from joinedload)
    # If the first flock has logs loaded, assume all do to avoid N+1 checks or partial loads
    has_eager_logs = len(flocks) > 0 and 'logs' in db.inspect(flocks[0]).attrs and db.inspect(flocks[0]).attrs.logs.history.has_changes() is False

    # Actually, we can just check if f.logs is populated without triggering lazy load?
    # But accessing f.logs triggers it if not loaded.
    # We can rely on the caller ensuring efficient loading.

    # Logic: If we rely on passed flocks having logs, we skip the query.
    # But get_iso_aggregated_data is a utility.
    # Let's check if we should query.

    # For now, let's optimize specifically for when we know we have logs (from executive_dashboard)
    # We can iterate and see.

    # Safe approach: Collect logs from flocks. If empty, query DB?
    # But querying DB is what we want to avoid if they ARE loaded.

    # Let's assume for this specific performance task that we want to avoid the redundant query.
    # We will build logs_by_flock from flock.logs.

    for f in flocks:
        # We access f.logs. If it was eager loaded, good. If not, it triggers a query (N+1).
        # But since we optimized executive_dashboard to use joinedload, this is fast.
        logs_by_flock[f.id] = f.logs

    for flock in flocks:
        logs = logs_by_flock.get(flock.id, [])
        hatch_records = hatch_by_flock.get(flock.id, [])

        daily_stats = enrich_flock_data(flock, logs, hatch_records)

        for d in daily_stats:
            d_date = d['date']
            # Strict Year Filter
            if d_date.year != filter_year:
                continue

            if d_date not in global_daily:
                global_daily[d_date] = {
                    'stock_f': 0, 'eggs': 0, 'mort_f': 0,
                    'chicks': 0, 'egg_set': 0,
                    'active_flocks': 0
                }

            # Check for Production Phase Logic
            is_prod = False
            if flock.production_start_date and d_date >= flock.production_start_date:
                is_prod = True
            elif flock.phase == 'Production':
                # Fallback: if no date set, assume phase is valid for all fetched logs?
                # No, historical logs might be rearing.
                # If eggs collected > 0, assume prod.
                if d['eggs_collected'] > 0: is_prod = True

            # Stock summation (Only if in production)
            if is_prod:
                global_daily[d_date]['stock_f'] += d['stock_female_start']
                global_daily[d_date]['mort_f'] += d['mortality_female']

            global_daily[d_date]['eggs'] += d['eggs_collected']

            if d.get('hatched_chicks'):
                global_daily[d_date]['chicks'] += d['hatched_chicks']
            if d.get('egg_set'):
                global_daily[d_date]['egg_set'] += d['egg_set']

            global_daily[d_date]['active_flocks'] += 1

    buckets = {'weekly': {}, 'monthly': {}, 'yearly': {}}
    sorted_dates = sorted(global_daily.keys())

    for d_date in sorted_dates:
        day_data = global_daily[d_date]

        isocal = d_date.isocalendar()
        week_key = f"{isocal[0]}-W{isocal[1]:02d}"
        month_key = d_date.strftime('%Y-%m')
        year_key = str(d_date.year)

        for p_type, p_key in [('weekly', week_key), ('monthly', month_key), ('yearly', year_key)]:
            if p_key not in buckets[p_type]:
                buckets[p_type][p_key] = {
                    'period': p_key,
                    'sum_stock_f': 0, 'days_with_stock': 0,
                    'total_eggs': 0, 'total_mort_f': 0,
                    'total_chicks': 0, 'total_set': 0,
                    'data_days': 0
                }

            b = buckets[p_type][p_key]
            b['total_eggs'] += day_data['eggs']
            b['total_mort_f'] += day_data['mort_f']
            b['total_chicks'] += day_data['chicks']
            b['total_set'] += day_data['egg_set']
            b['data_days'] += 1
            b['sum_stock_f'] += day_data['stock_f']

    results = {'weekly': [], 'monthly': [], 'yearly': []}

    for p_type in ['weekly', 'monthly', 'yearly']:
        sorted_keys = sorted(buckets[p_type].keys(), reverse=True)

        for k in sorted_keys:
            b = buckets[p_type][k]

            avg_stock = b['sum_stock_f'] / b['data_days'] if b['data_days'] > 0 else 0
            egg_prod_pct = (b['total_eggs'] / b['sum_stock_f'] * 100) if b['sum_stock_f'] > 0 else 0
            mort_pct = (b['total_mort_f'] / avg_stock * 100) if avg_stock > 0 else 0
            hatch_pct = (b['total_chicks'] / b['total_set'] * 100) if b['total_set'] > 0 else 0

            results[p_type].append({
                'period': b['period'],
                'avg_female_stock': int(avg_stock),
                'total_eggs': b['total_eggs'],
                'total_chicks': b['total_chicks'],
                'mortality_pct': round(mort_pct, 2),
                'hatchability_pct': round(hatch_pct, 2),
                'egg_production_pct': round(egg_prod_pct, 2)
            })

    return results

def get_hatchery_analytics():
    today = date.today()

    # Common filter for Active Production Flocks
    flock_filter = and_(Flock.status == 'Active', Flock.phase == 'Production')

    # Previous Hatch
    # Max date <= today with hatched_chicks > 0
    last_hatch_date_query = db.session.query(func.max(Hatchability.hatching_date)).join(Flock).filter(
        Hatchability.hatching_date <= today,
        Hatchability.hatched_chicks > 0,
        flock_filter
    ).scalar()

    last_hatch = None
    if last_hatch_date_query:
        last_records = Hatchability.query.join(Flock).filter(
            Hatchability.hatching_date == last_hatch_date_query,
            flock_filter
        ).all()

        total_h = sum(r.hatched_chicks for r in last_records)
        total_s = sum(r.egg_set for r in last_records)
        h_pct = (total_h / total_s * 100) if total_s > 0 else 0.0
        last_hatch = {
            'date': last_hatch_date_query,
            'total_hatched': total_h,
            'hatch_pct': h_pct
        }

    # Next Hatch
    # Min date >= today (or > last_hatch_date if today was processed as Previous)
    next_filter_condition = Hatchability.hatching_date >= today
    if last_hatch and last_hatch['date'] == today:
        next_filter_condition = Hatchability.hatching_date > today

    next_hatch_date_query = db.session.query(func.min(Hatchability.hatching_date)).join(Flock).filter(
        next_filter_condition,
        Hatchability.egg_set > 0,
        flock_filter
    ).scalar()

    next_hatch = None
    if next_hatch_date_query:
        next_records = Hatchability.query.join(Flock).filter(
            Hatchability.hatching_date == next_hatch_date_query,
            flock_filter
        ).all()

        # Calculate Forecast
        all_standards = Standard.query.all()
        std_map = {getattr(s, 'week'): getattr(s, 'std_hatchability', 0.0) for s in all_standards if hasattr(s, 'week')}

        total_forecast = 0
        for r in next_records:
            age_days = (next_hatch_date_query - r.flock.intake_date).days
            age_week = 0 if age_days == 0 else ((age_days - 1) // 7) + 1 if age_days > 0 else (age_days // 7)
            std_hatch = std_map.get(age_week)
            if std_hatch is None: std_hatch = 0.0
            forecast = r.egg_set * (std_hatch / 100.0)
            total_forecast += forecast

        next_hatch = {
            'date': next_hatch_date_query,
            'forecast': int(total_forecast)
        }

    return last_hatch, next_hatch

@app.route('/executive_dashboard')
@login_required
def executive_dashboard():
    # Role Check: Admin or Management
    if not current_user.role == 'Admin' and current_user.role != 'Management':
        flash("Access Denied: Executive View Only.", "danger")
        return redirect(url_for('index'))

    # --- Farm Data ---
    active_flocks = Flock.query.options(joinedload(Flock.logs).joinedload(DailyLog.partition_weights), joinedload(Flock.logs).joinedload(DailyLog.photos), joinedload(Flock.logs).joinedload(DailyLog.clinical_notes_list), joinedload(Flock.house)).filter_by(status='Active').all()

    if active_flocks:
            active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else ''))

    today = date.today()

    # Inventory Check
    low_stock_items = InventoryItem.query.filter(InventoryItem.current_stock < InventoryItem.min_stock_level).all()
    low_stock_count = len(low_stock_items)
    normal_stock_items = InventoryItem.query.filter(InventoryItem.current_stock >= InventoryItem.min_stock_level).all()

    # Pre-fetch Hatchability Data (Optimization: Bulk Fetch)
    flock_ids = [f.id for f in active_flocks]
    all_hatch_records = Hatchability.query.filter(Hatchability.flock_id.in_(flock_ids)).order_by(Hatchability.setting_date.desc()).all()

    flock_hatch_map = {}
    for h in all_hatch_records:
        if h.flock_id not in flock_hatch_map:
            flock_hatch_map[h.flock_id] = {
                'latest': h,  # First record is latest due to ordering
                'hatched_sum': 0,
                'set_sum': 0,
                'records': []
            }
        flock_hatch_map[h.flock_id]['hatched_sum'] += (h.hatched_chicks or 0)
        flock_hatch_map[h.flock_id]['set_sum'] += (h.egg_set or 0)
        flock_hatch_map[h.flock_id]['records'].append(h)

    for f in active_flocks:
        h_data = flock_hatch_map.get(f.id)
        hatch_recs = h_data['records'] if h_data else []

        daily_stats = enrich_flock_data(f, f.logs, hatchability_data=hatch_recs)
        f.enriched_data = daily_stats # Cache for ISO Report with hatch data

        # Hatchery Enrichment
        if h_data:
            latest_hatch = h_data['latest']
            total_h = h_data['hatched_sum']
            total_s = h_data['set_sum']
        else:
            latest_hatch = None
            total_h = 0
            total_s = 0

        f.latest_hatch = latest_hatch
        f.latest_hatch_pct = latest_hatch.hatchability_pct if latest_hatch else 0.0

        f.cum_hatch_pct = (total_h / total_s * 100) if total_s > 0 else 0.0

        f.rearing_mort_m_pct = 0
        f.rearing_mort_f_pct = 0
        f.prod_mort_m_pct = 0
        f.prod_mort_f_pct = 0
        f.male_ratio_pct = 0
        f.has_log_today = False

        # Age
        days_age = (today - f.intake_date).days
        f.age_weeks = 0 if days_age == 0 else ((days_age - 1) // 7) + 1 if days_age > 0 else 0
        f.age_days = ((days_age - 1) % 7) + 1 if days_age > 0 else 0
        f.current_week = 0 if days_age == 0 else ((days_age - 1) // 7) + 1 if days_age > 0 else 0

        # Stats
        if daily_stats:
            last = daily_stats[-1]
            if last['date'] == today:
                f.has_log_today = True

            if getattr(f, 'calculated_phase', f.phase) in REARING_PHASES:
                f.rearing_mort_m_pct = last['mortality_cum_male_pct']
                f.rearing_mort_f_pct = last['mortality_cum_female_pct']
            else:
                f.prod_mort_m_pct = last['mortality_cum_male_pct']
                f.prod_mort_f_pct = last['mortality_cum_female_pct']

            if last['male_ratio_stock']:
                f.male_ratio_pct = last['male_ratio_stock']

        # Daily Stats & Trends
        f.daily_stats = {
            'mort_m_pct': 0, 'mort_f_pct': 0, 'egg_pct': 0,
            'mort_m_trend': 'flat', 'mort_f_trend': 'flat', 'egg_trend': 'flat',
            'mort_m_diff': 0, 'mort_f_diff': 0, 'egg_diff': 0,
            'has_today': False,
            'show_data': False,
            'data_date': None
        }

        stats_map = { d['date']: d for d in daily_stats }
        stats_today = stats_map.get(today)

        # Determine Display Data (Today or Latest)
        display_data = None
        if stats_today:
            f.daily_stats['has_today'] = True
            display_data = stats_today
        elif daily_stats:
            display_data = daily_stats[-1]

        if display_data:
            f.daily_stats['show_data'] = True
            f.daily_stats['data_date'] = display_data['date']

            f.daily_stats['mort_m_pct'] = display_data['mortality_male_pct']
            f.daily_stats['mort_f_pct'] = display_data['mortality_female_pct']
            f.daily_stats['egg_pct'] = display_data['egg_prod_pct']

            # Trend Calculation (vs Previous Day of DATA DATE)
            stats_prev = None
            if display_data in daily_stats:
                idx = daily_stats.index(display_data)
                if idx > 0:
                    stats_prev = daily_stats[idx-1]
            else:
                prev_date = display_data['date'] - timedelta(days=1)
                stats_prev = stats_map.get(prev_date)

            if stats_prev:
                f.daily_stats['mort_m_diff'] = display_data['mortality_male_pct'] - stats_prev['mortality_male_pct']
                f.daily_stats['mort_f_diff'] = display_data['mortality_female_pct'] - stats_prev['mortality_female_pct']
                f.daily_stats['egg_diff'] = display_data['egg_prod_pct'] - stats_prev['egg_prod_pct']

                if round(f.daily_stats['mort_m_diff'], 2) > 0: f.daily_stats['mort_m_trend'] = 'up'
                elif round(f.daily_stats['mort_m_diff'], 2) < 0: f.daily_stats['mort_m_trend'] = 'down'

                if round(f.daily_stats['mort_f_diff'], 2) > 0: f.daily_stats['mort_f_trend'] = 'up'
                elif round(f.daily_stats['mort_f_diff'], 2) < 0: f.daily_stats['mort_f_trend'] = 'down'

                if round(f.daily_stats['egg_diff'], 2) > 0: f.daily_stats['egg_trend'] = 'up'
                elif round(f.daily_stats['egg_diff'], 2) < 0: f.daily_stats['egg_trend'] = 'down'

    # Analytics: Previous & Next Hatch Dates
    last_hatch, next_hatch = get_hatchery_analytics()

    # --- New ISO Reports ---
    # Year Filter Logic
    available_years_query = db.session.query(func.extract('year', DailyLog.date)).distinct().all()
    available_years = sorted([int(y[0]) for y in available_years_query if y[0]], reverse=True)
    if not available_years:
        available_years = [today.year]

    selected_year = request.args.get('year', type=int)
    if not selected_year:
        selected_year = available_years[0] if available_years else today.year

    active_tab = request.args.get('active_tab', 'overview')

    # Phase 3 Optimization: Python Enrichment Engine to match SSOT
    all_enriched_data = []

    # Use the active_flocks we already fetched and enriched above
    for flock in active_flocks:
        if hasattr(flock, 'enriched_data') and flock.enriched_data:
            # Filter for the selected year and append
            enriched_year = [d for d in flock.enriched_data if d['date'].year == selected_year]
            all_enriched_data.extend(enriched_year)

    weekly_agg = aggregate_weekly_metrics(all_enriched_data)
    monthly_agg = aggregate_monthly_metrics(all_enriched_data)

    iso_data = {
        'weekly': [],
        'monthly': [],
        'yearly': []
    }

    # Format weekly
    for ws in reversed(weekly_agg):  # frontend expects descending
        avg_hen = ws['stock_female_start'] - ((ws['mortality_female'] + ws['culls_female']) / 2)

        iso_data['weekly'].append({
            'period': f"Week {ws['week']}",
            'avg_female_stock': int(avg_hen),
            'total_eggs': ws['eggs_collected'],
            'total_chicks': ws['hatched_chicks'],
            'mortality_pct': ws['mortality_female_pct'],
            'hatchability_pct': ws['hatchability_pct'],
            'egg_production_pct': ws['egg_prod_pct']
        })

    # Format monthly
    for ms in reversed(monthly_agg):
        avg_hen = ms['stock_female_start'] - ((ms['mortality_female'] + ms['culls_female']) / 2)

        iso_data['monthly'].append({
            'period': ms['month'],
            'avg_female_stock': int(avg_hen),
            'total_eggs': ms['eggs_collected'],
            'total_chicks': ms['hatched_chicks'],
            'mortality_pct': ms['mortality_female_pct'],
            'hatchability_pct': ms['hatchability_pct'],
            'egg_production_pct': ms['egg_prod_pct']
        })

    # Build yearly aggregation manually since metrics.py doesn't have aggregate_yearly_metrics
    yearly_stats = {}
    for d in all_enriched_data:
        y_key = str(d['date'].year)
        if y_key not in yearly_stats:
            yearly_stats[y_key] = {
                'period': y_key,
                'count': 0,
                'stock_female_start': d['stock_female_start'],
                'mortality_female': 0,
                'culls_female': 0,
                'eggs_collected': 0,
                'hatched_chicks': 0,
                'egg_set': 0
            }

        ys = yearly_stats[y_key]
        ys['count'] += 1
        ys['mortality_female'] += d['mortality_female']
        ys['culls_female'] += d['culls_female']
        ys['eggs_collected'] += d['eggs_collected']
        if d.get('hatched_chicks'): ys['hatched_chicks'] += d['hatched_chicks']
        if d.get('egg_set'): ys['egg_set'] += d['egg_set']

    for y_key in sorted(yearly_stats.keys(), reverse=True):
        ys = yearly_stats[y_key]
        avg_hen = ys['stock_female_start'] - ((ys['mortality_female'] + ys['culls_female']) / 2)
        mortality_pct = (ys['mortality_female'] / ys['stock_female_start'] * 100) if ys['stock_female_start'] > 0 else 0
        egg_prod_pct = (ys['eggs_collected'] / (avg_hen * ys['count'])) * 100 if (avg_hen * ys['count']) > 0 else 0
        hatchability_pct = (ys['hatched_chicks'] / ys['egg_set'] * 100) if ys['egg_set'] > 0 else 0

        iso_data['yearly'].append({
            'period': y_key,
            'avg_female_stock': int(avg_hen),
            'total_eggs': ys['eggs_collected'],
            'total_chicks': ys['hatched_chicks'],
            'mortality_pct': mortality_pct,
            'hatchability_pct': hatchability_pct,
            'egg_production_pct': egg_prod_pct
        })

    # Monthly Inventory Usage Calculation
    current_month_start = today.replace(day=1)
    if current_month_start.month == 1:
        last_month_start = current_month_start.replace(year=current_month_start.year - 1, month=12)
    else:
        last_month_start = current_month_start.replace(month=current_month_start.month - 1)

    inventory_items = InventoryItem.query.all()
    inventory_usage = []

    # We will get logs for current and last month
    logs_this_month = InventoryTransaction.query.filter(
        InventoryTransaction.transaction_date >= current_month_start,
        InventoryTransaction.transaction_type.in_(['Usage', 'Waste'])
    ).all()

    logs_last_month = InventoryTransaction.query.filter(
        InventoryTransaction.transaction_date >= last_month_start,
        InventoryTransaction.transaction_date < current_month_start,
        InventoryTransaction.transaction_type.in_(['Usage', 'Waste'])
    ).all()

    for item in inventory_items:
        used_this = sum(log.quantity for log in logs_this_month if log.inventory_item_id == item.id)
        used_last = sum(log.quantity for log in logs_last_month if log.inventory_item_id == item.id)

        inventory_usage.append({
            'name': item.name,
            'type': item.type,
            'current_stock': item.current_stock,
            'unit': item.unit,
            'used_this_month': round(used_this, 2),
            'used_last_month': round(used_last, 2)
        })

    return render_template('executive_dashboard.html',
                           active_flocks=active_flocks,
                           last_hatch=last_hatch,
                           next_hatch=next_hatch,
                           current_month=today.strftime('%B %Y'),
                           today=today,
                           inventory_usage=inventory_usage,
                           iso_data=iso_data,
                           available_years=available_years,
                           selected_year=selected_year,
                           active_tab=active_tab)


@app.route('/executive/flock_select')
@login_required
def flock_detail_readonly_select():
    # Role Check: Admin or Management
    if not current_user.role == 'Admin' and current_user.role != 'Management':
        flash("Access Denied: Executive View Only.", "danger")
        return redirect(url_for('index'))

    active_flocks = Flock.query.options(joinedload(Flock.house)).filter_by(status='Active').all()

    if active_flocks:
            active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else ''))

    if not active_flocks:
        flash("No active flocks found.", "warning")
        return redirect(url_for('executive_dashboard'))

    return render_template('flock_detail_readonly_select.html', active_flocks=active_flocks)

@app.route('/executive/flock/<int:id>')
@login_required
def executive_flock_detail(id):
    # Role Check: Admin or Management
    if not current_user.role == 'Admin' and current_user.role != 'Management':
        flash("Access Denied: Executive View Only.", "danger")
        return redirect(url_for('index'))

    active_flocks = Flock.query.options(joinedload(Flock.house)).filter_by(status='Active').all()

    if active_flocks:
            active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else ''))

    flock = Flock.query.options(joinedload(Flock.house)).filter_by(id=id).first_or_404()
    logs = DailyLog.query.options(joinedload(DailyLog.partition_weights), joinedload(DailyLog.photos), joinedload(DailyLog.clinical_notes_list)).filter_by(flock_id=id).order_by(DailyLog.date.asc()).all()

    gs = GlobalStandard.query.first()
    if not gs:
        gs = GlobalStandard()
        db.session.add(gs)
        safe_commit()

    # --- Standards Setup ---
    all_standards = Standard.query.all()
    std_map = {getattr(s, 'week'): s for s in all_standards if hasattr(s, 'week')} # Bio Map
    prod_std_map = {getattr(s, 'production_week'): s for s in all_standards if hasattr(s, 'production_week') and getattr(s, 'production_week')} # Prod Map

    std_hatch_map = {getattr(s, 'week'): (getattr(s, 'std_hatchability', 0.0) or 0.0) for s in all_standards if hasattr(s, 'week')}

    # --- Fetch Hatch Data ---
    hatch_records = Hatchability.query.filter_by(flock_id=id).order_by(Hatchability.setting_date.desc()).all()

    # --- Metrics Engine ---
    daily_stats = enrich_flock_data(flock, logs, hatch_records)

    # --- Calculate Summary Tab Data ---
    summary_dashboard, summary_table = calculate_flock_summary(flock, daily_stats)

    # Inject Shifted Standard
    for d in daily_stats:
        # Biological Standards (Mortality, BW)
        std_bio = std_map.get(d['week'])
        d['std_mortality_male'] = (std_bio.std_mortality_male if std_bio and std_bio.std_mortality_male is not None else 0.0)
        d['std_mortality_female'] = (std_bio.std_mortality_female if std_bio and std_bio.std_mortality_female is not None else 0.0)

        # Production Standards (Egg Prod)
        prod_std = None
        if d.get('production_week'):
            prod_std = prod_std_map.get(d['production_week'])

        d['std_egg_prod'] = (prod_std.std_egg_prod if prod_std and prod_std.std_egg_prod is not None else 0.0)
        d['std_hatching_egg_pct'] = (prod_std.std_hatching_egg_pct if prod_std and prod_std.std_hatching_egg_pct is not None else 0.0)

    weekly_stats = aggregate_weekly_metrics(daily_stats)

    for ws in weekly_stats:
        # Biological Standards
        std_bio = std_map.get(ws['week'])
        ws['std_mortality_male'] = (std_bio.std_mortality_male if std_bio and std_bio.std_mortality_male is not None else 0.0)
        ws['std_mortality_female'] = (std_bio.std_mortality_female if std_bio and std_bio.std_mortality_female is not None else 0.0)

        # Production Standards
        prod_std = None
        if ws.get('production_week'):
            prod_std = prod_std_map.get(ws['production_week'])

        ws['std_egg_prod'] = (prod_std.std_egg_prod if prod_std and prod_std.std_egg_prod is not None else 0.0)
        ws['std_hatching_egg_pct'] = (prod_std.std_hatching_egg_pct if prod_std and prod_std.std_hatching_egg_pct is not None else 0.0)

    medications = Medication.query.filter_by(flock_id=id).all()
    vacs = Vaccine.query.filter_by(flock_id=id).filter(Vaccine.actual_date != None).all()

    # 1. Enriched Logs
    enriched_logs = []
    def scale_pct(val):
        if val is None: return None
        if 0 < val <= 1.0: return val * 100.0
        return val

    for d in daily_stats:
        log = d['log']
        lighting_hours = 0
        if log.light_on_time and log.light_off_time:
            try:
                fmt = '%H:%M'
                t1 = datetime.strptime(log.light_on_time, fmt)
                t2 = datetime.strptime(log.light_off_time, fmt)
                diff = (t2 - t1).total_seconds() / 3600
                if diff < 0: diff += 24
                lighting_hours = round(diff, 1)
            except: pass

        active_meds = []
        for m in medications:
            if m.start_date <= log.date:
                if m.end_date is None or m.end_date >= log.date:
                    active_meds.append(m.drug_name)
        meds_str = ", ".join(active_meds)

        cleanup_duration_mins = None
        if log.feed_cleanup_start and log.feed_cleanup_end:
            try:
                from analytics import calculate_feed_cleanup_duration
                cleanup_duration_mins = calculate_feed_cleanup_duration(log.feed_cleanup_start, log.feed_cleanup_end)
            except Exception:
                pass
        feed_cleanup_hours = round(cleanup_duration_mins / 60.0, 1) if cleanup_duration_mins else None

        enriched_logs.append({
            'log': log,
            'stock_male': d.get('stock_male_prod_end', 0) + d.get('stock_male_hosp_end', 0),
            'stock_female': d.get('stock_female_prod_end', 0) + d.get('stock_female_hosp_end', 0),
            'lighting_hours': lighting_hours,
            'medications': meds_str,
            'egg_prod_pct': d['egg_prod_pct'],
            'total_feed': d['feed_total_kg'],
            'feed_cleanup_hours': feed_cleanup_hours,
            'egg_data': {
                'jumbo': d['cull_eggs_jumbo'],
                'jumbo_pct': d['cull_eggs_jumbo_pct'],
                'small': d['cull_eggs_small'],
                'small_pct': d['cull_eggs_small_pct'],
                'crack': d['cull_eggs_crack'],
                'crack_pct': d['cull_eggs_crack_pct'],
                'abnormal': d['cull_eggs_abnormal'],
                'abnormal_pct': d['cull_eggs_abnormal_pct'],
                'hatching': d['hatch_eggs'],
                'hatching_pct': d['hatch_egg_pct'],
                'total_culls': d['cull_eggs_total'],
                'total_culls_pct': d['cull_eggs_pct']
            }
        })

    # 2. Weekly Data
    weekly_data = []
    for ws in weekly_stats:
        w_item = {
            'week': ws['week'],
            'mortality_male': ws['mortality_male'],
            'mortality_female': ws['mortality_female'],
            'culls_male': ws['culls_male'],
            'culls_female': ws['culls_female'],
            'eggs': ws['eggs_collected'],
            'hatch_eggs_sum': ws['hatch_eggs'],
            'cull_eggs_total': ws['cull_eggs_jumbo'] + ws['cull_eggs_small'] + ws['cull_eggs_crack'] + ws['cull_eggs_abnormal'],
            'mort_pct_m': ws['mortality_male_pct'],
            'mort_pct_f': ws['mortality_female_pct'],
            'cull_pct_m': ws['culls_male_pct'],
            'cull_pct_f': ws['culls_female_pct'],
            'egg_prod_pct': ws['egg_prod_pct'],
            'hatching_egg_pct': ws['hatch_egg_pct'],
            'cull_eggs_jumbo': ws['cull_eggs_jumbo'],
            'cull_eggs_jumbo_pct': ws['cull_eggs_jumbo_pct'] * 100 if ws.get('cull_eggs_jumbo_pct') else 0,
            'cull_eggs_small': ws['cull_eggs_small'],
            'cull_eggs_small_pct': ws['cull_eggs_small_pct'] * 100 if ws.get('cull_eggs_small_pct') else 0,
            'cull_eggs_crack': ws['cull_eggs_crack'],
            'cull_eggs_crack_pct': ws['cull_eggs_crack_pct'] * 100 if ws.get('cull_eggs_crack_pct') else 0,
            'cull_eggs_abnormal': ws['cull_eggs_abnormal'],
            'cull_eggs_abnormal_pct': ws['cull_eggs_abnormal_pct'] * 100 if ws.get('cull_eggs_abnormal_pct') else 0,
            'avg_bw_male': round_to_whole(ws['body_weight_male']),
            'avg_bw_female': round_to_whole(ws['body_weight_female']),
            'notes': ws['notes'],
            'photos': ws['photos']
        }
        weekly_data.append(w_item)

    # 3. Chart Data (Daily)
    chart_data = {
        'dates': [d['date'].strftime('%Y-%m-%d') for d in daily_stats],
        'ages': [d['log'].age_week_day for d in daily_stats],
        'mortality_cum_male': [round(d['mortality_cum_male_pct'], 2) for d in daily_stats],
        'mortality_cum_female': [round(d['mortality_cum_female_pct'], 2) for d in daily_stats],
        'mortality_daily_male': [round(d['mortality_male_pct'], 2) for d in daily_stats],
        'mortality_daily_female': [round(d['mortality_female_pct'], 2) for d in daily_stats],
        'std_mortality_male': [round(d['std_mortality_male'], 3) for d in daily_stats],
        'std_mortality_female': [round(d['std_mortality_female'], 3) for d in daily_stats],
        'culls_daily_male': [round(d['culls_male_pct'], 2) for d in daily_stats],
        'culls_daily_female': [round(d['culls_female_pct'], 2) for d in daily_stats],
        'egg_prod': [round(d['egg_prod_pct'], 2) for d in daily_stats],
        'std_egg_prod': [round(d['std_egg_prod'], 2) for d in daily_stats],
        'hatch_egg_pct': [round(d['hatch_egg_pct'], 2) for d in daily_stats],
        'std_hatching_egg_pct': [round(d['std_hatching_egg_pct'], 2) for d in daily_stats],
        'cull_eggs_jumbo_pct': [round(d['cull_eggs_jumbo_pct'], 2) for d in daily_stats],
        'cull_eggs_small_pct': [round(d['cull_eggs_small_pct'], 2) for d in daily_stats],
        'cull_eggs_crack_pct': [round(d['cull_eggs_crack_pct'], 2) for d in daily_stats],
        'cull_eggs_abnormal_pct': [round(d['cull_eggs_abnormal_pct'], 2) for d in daily_stats],
        'male_ratio': [round(d['male_ratio_stock'], 2) if d['male_ratio_stock'] else 0 for d in daily_stats],
        'bw_male_std': [d['log'].standard_bw_male if d['log'].standard_bw_male > 0 else None for d in daily_stats],
        'bw_female_std': [d['log'].standard_bw_female if d['log'].standard_bw_female > 0 else None for d in daily_stats],
        'unif_male': [scale_pct(d['uniformity_male']) if d['uniformity_male'] > 0 else None for d in daily_stats],
        'unif_female': [scale_pct(d['uniformity_female']) if d['uniformity_female'] > 0 else None for d in daily_stats],
        'bw_f': [d['body_weight_female'] if d['body_weight_female'] > 0 else None for d in daily_stats],
        'bw_m': [d['body_weight_male'] if d['body_weight_male'] > 0 else None for d in daily_stats],
        'water_per_bird': [round(d['water_per_bird'], 1) if d['water_per_bird'] >= 0 else None for d in daily_stats],
        'water_feed_ratio': [round(d.get('water_feed_ratio'), 2) if d.get('water_feed_ratio') is not None and d.get('water_feed_ratio') >= 0 else None for d in daily_stats],
        'feed_male_gp_bird': [round(d['feed_male_gp_bird'], 1) for d in daily_stats],
        'feed_female_gp_bird': [round(d['feed_female_gp_bird'], 1) for d in daily_stats],
        'flushing': [d['log'].flushing for d in daily_stats],
        'notes': [],
        'medication_active': [],
        'medication_names': []
    }

    for i in range(1, 9):
        chart_data[f'bw_M{i}'] = []
        chart_data[f'bw_F{i}'] = []

    for d in daily_stats:
        log = d['log']
        p_map = {pw.partition_name: pw.body_weight for pw in log.partition_weights}
        for i in range(1, 9):
            val_m = p_map.get(f'M{i}', 0)
            if val_m == 0 and i <= 2: val_m = getattr(log, f'bw_male_p{i}', 0)
            chart_data[f'bw_M{i}'].append(val_m if val_m > 0 else None)
            val_f = p_map.get(f'F{i}', 0)
            if val_f == 0 and i <= 4: val_f = getattr(log, f'bw_female_p{i}', 0)
            chart_data[f'bw_F{i}'].append(val_f if val_f > 0 else None)

        note_obj = None

        # Construct Note
        note_parts = []
        if log.flushing: note_parts.append("[FLUSHING]")
        if log.clinical_notes: note_parts.append(log.clinical_notes)

        # Meds
        active_meds = [m.drug_name for m in medications if m.start_date <= log.date and (m.end_date is None or m.end_date >= log.date)]
        chart_data['medication_active'].append(len(active_meds) > 0)
        chart_data['medication_names'].append(", ".join(active_meds) if active_meds else "")

        # User requested to remove medication from notes, so we don't append to note_parts
        # if active_meds: note_parts.append("Meds: " + ", ".join(active_meds))

        # Vacs
        done_vacs = [v.vaccine_name for v in vacs if v.actual_date == log.date]
        if done_vacs: note_parts.append("Vac: " + ", ".join(done_vacs))

        has_photos = len(log.photos) > 0
        if note_parts or has_photos:
            photo_list = []
            for p in log.photos:
                photo_list.append({
                    'url': url_for('uploaded_file', filename=os.path.basename(p.file_path)),
                    'name': p.original_filename or 'Photo'
                })

            note_obj = {
                'note': " | ".join(note_parts),
                'photos': photo_list
            }

        chart_data['notes'].append(note_obj)

    # 4. Chart Data (Weekly)
    daily_by_week = {}
    for d in daily_stats:
        if d['week'] not in daily_by_week: daily_by_week[d['week']] = []
        daily_by_week[d['week']].append(d)

    weekly_map = {ws['week']: ws for ws in weekly_stats}
    chart_data_weekly = {
        'dates': [],
        'ages': [],
        'mortality_cum_male': [], 'mortality_cum_female': [],
        'mortality_weekly_male': [], 'mortality_weekly_female': [],
        'std_mortality_male': [], 'std_mortality_female': [],
        'culls_weekly_male': [], 'culls_weekly_female': [],
        'avg_bw_male': [], 'avg_bw_female': [],
        'egg_prod': [],
        'bw_male_std': [], 'bw_female_std': [],
        'unif_male': [], 'unif_female': [],
        'notes': []
    }
    for i in range(1, 9):
        chart_data_weekly[f'bw_M{i}'] = []
        chart_data_weekly[f'bw_F{i}'] = []

    for w in sorted(weekly_map.keys()):
        ws = weekly_map[w]
        last_day = daily_by_week[w][-1]

        chart_data_weekly['dates'].append(f"Week {w}")
        chart_data_weekly['mortality_cum_male'].append(round(last_day['mortality_cum_male_pct'], 2))
        chart_data_weekly['mortality_cum_female'].append(round(last_day['mortality_cum_female_pct'], 2))
        chart_data_weekly['mortality_weekly_male'].append(round(ws['mortality_male_pct'], 2))
        chart_data_weekly['mortality_weekly_female'].append(round(ws['mortality_female_pct'], 2))
        chart_data_weekly['culls_weekly_male'].append(round(ws['culls_male_pct'], 2))
        chart_data_weekly['culls_weekly_female'].append(round(ws['culls_female_pct'], 2))
        chart_data_weekly['avg_bw_male'].append(round_to_whole(ws['body_weight_male']) if ws['body_weight_male'] > 0 else None)
        chart_data_weekly['avg_bw_female'].append(round_to_whole(ws['body_weight_female']) if ws['body_weight_female'] > 0 else None)
        chart_data_weekly['egg_prod'].append(round(ws['egg_prod_pct'], 2))
        chart_data_weekly['std_egg_prod'] = chart_data_weekly.get('std_egg_prod', [])
        chart_data_weekly['std_egg_prod'].append(round(ws['std_egg_prod'], 2))

        chart_data_weekly['hatch_egg_pct'] = chart_data_weekly.get('hatch_egg_pct', [])
        chart_data_weekly['hatch_egg_pct'].append(round(ws['hatch_egg_pct'], 2))

        chart_data_weekly['std_hatching_egg_pct'] = chart_data_weekly.get('std_hatching_egg_pct', [])
        chart_data_weekly['std_hatching_egg_pct'].append(round(ws['std_hatching_egg_pct'], 2))

        chart_data_weekly['cull_eggs_jumbo_pct'] = chart_data_weekly.get('cull_eggs_jumbo_pct', [])
        chart_data_weekly['cull_eggs_jumbo_pct'].append(round(ws['cull_eggs_jumbo_pct'], 2))

        chart_data_weekly['cull_eggs_small_pct'] = chart_data_weekly.get('cull_eggs_small_pct', [])
        chart_data_weekly['cull_eggs_small_pct'].append(round(ws['cull_eggs_small_pct'], 2))

        chart_data_weekly['cull_eggs_crack_pct'] = chart_data_weekly.get('cull_eggs_crack_pct', [])
        chart_data_weekly['cull_eggs_crack_pct'].append(round(ws['cull_eggs_crack_pct'], 2))

        chart_data_weekly['cull_eggs_abnormal_pct'] = chart_data_weekly.get('cull_eggs_abnormal_pct', [])
        chart_data_weekly['cull_eggs_abnormal_pct'].append(round(ws['cull_eggs_abnormal_pct'], 2))

        # Standard BW - Use Biological Age (w)
        std_bio = std_map.get(w)
        chart_data_weekly['bw_male_std'].append(std_bio.std_bw_male if std_bio and std_bio.std_bw_male > 0 else None)
        chart_data_weekly['bw_female_std'].append(std_bio.std_bw_female if std_bio and std_bio.std_bw_female > 0 else None)

        chart_data_weekly['unif_male'].append(scale_pct(ws['uniformity_male']) if ws['uniformity_male'] > 0 else None)
        chart_data_weekly['unif_female'].append(scale_pct(ws['uniformity_female']) if ws['uniformity_female'] > 0 else None)

        chart_data_weekly['water_per_bird'] = chart_data_weekly.get('water_per_bird', [])
        chart_data_weekly['water_per_bird'].append(round(ws['water_per_bird'], 1) if ws.get('water_per_bird', 0) >= 0 else None)
        chart_data_weekly['water_feed_ratio'] = chart_data_weekly.get('water_feed_ratio', [])
        chart_data_weekly['water_feed_ratio'].append(round(ws.get('water_feed_ratio'), 2) if ws.get('water_feed_ratio') is not None and ws.get('water_feed_ratio') >= 0 else None)

        chart_data_weekly['feed_male_gp_bird'] = chart_data_weekly.get('feed_male_gp_bird', [])
        chart_data_weekly['feed_male_gp_bird'].append(round(ws['feed_male_gp_bird'], 1))

        chart_data_weekly['feed_female_gp_bird'] = chart_data_weekly.get('feed_female_gp_bird', [])
        chart_data_weekly['feed_female_gp_bird'].append(round(ws['feed_female_gp_bird'], 1))

        for i in range(1, 9):
            chart_data_weekly[f'bw_M{i}'].append(None)
            chart_data_weekly[f'bw_F{i}'].append(None)

        # Aggregate Weekly Notes/Photos
        week_notes = []
        week_photos = []

        # From Daily Logs
        if w in daily_by_week:
            week_logs_data = daily_by_week[w]
            if week_logs_data:
                w_start = week_logs_data[0]['date']
                w_end = week_logs_data[-1]['date']

                for d in week_logs_data:
                    log = d['log']
                    if log.clinical_notes:
                        week_notes.append(f"{log.date.strftime('%d/%m')}: {log.clinical_notes}")

                    for p in log.photos:
                        week_photos.append({
                            'url': url_for('uploaded_file', filename=os.path.basename(p.file_path)),
                            'name': f"{log.date.strftime('%d/%m')} {p.original_filename or 'Photo'}"
                        })

                # Meds
                w_meds = set()
                for m in medications:
                    if m.start_date <= w_end and (m.end_date is None or m.end_date >= w_start):
                        w_meds.add(m.drug_name)
                if w_meds: week_notes.append("Meds: " + ", ".join(w_meds))

                # Vacs
                w_vacs = set()
                for v in vacs:
                    if v.actual_date and w_start <= v.actual_date <= w_end:
                        w_vacs.add(v.vaccine_name)
                if w_vacs: week_notes.append("Vac: " + ", ".join(w_vacs))

        if week_notes or week_photos:
            chart_data_weekly['notes'].append({
                'note': " | ".join(week_notes),
                'photos': week_photos
            })
        else:
            chart_data_weekly['notes'].append(None)

    # 5. Current Stats
    if daily_stats:
        last = daily_stats[-1]
        current_stats = {
            'male_prod': last.get('stock_male_prod_end', 0),
            'female_prod': last.get('stock_female_prod_end', 0),
            'male_hosp': last.get('stock_male_hosp_end', 0),
            'female_hosp': last.get('stock_female_hosp_end', 0),
            'male_ratio': last['male_ratio_stock'] if last.get('male_ratio_stock') else 0
        }
    else:
        current_stats = {
            'male_prod': flock.intake_male,
            'female_prod': flock.intake_female,
            'male_hosp': 0,
            'female_hosp': 0,
            'male_ratio': (flock.intake_male / flock.intake_female * 100) if flock.intake_female > 0 else 0
        }

    weekly_data.reverse()

    # Pre-check available reports for this flock
    from werkzeug.utils import secure_filename
    reports_dir = os.path.join(app.root_path, 'static', 'reports')
    available_reports = set()
    if os.path.exists(reports_dir):
        prefix_to_match = f"_{secure_filename(flock.house.name)}_"
        for f in os.listdir(reports_dir):
            if prefix_to_match in f and f.endswith(".jpg"):
                date_str = f.split("_")[0]
                available_reports.add(date_str)

    return render_template('flock_detail_readonly.html',
                           flock=flock,
                           available_reports=available_reports,
                           logs=list(reversed(enriched_logs)),
                           weekly_data=weekly_data,
                           chart_data=chart_data,
                           chart_data_weekly=chart_data_weekly,
                           current_stats=current_stats,
                           global_std=gs,
                           active_flocks=active_flocks,
                           hatch_records=hatch_records,
                           summary_dashboard=summary_dashboard,
                           summary_table=summary_table,
                           std_hatch_map=std_hatch_map)


@app.route('/api/floating_notes/<int:flock_id>', methods=['GET'])
@login_required
@dept_required(['Farm', 'Admin', 'Management'])
def get_floating_notes(flock_id):
    notes = FloatingNote.query.filter_by(flock_id=flock_id).all()
    result = []
    for note in notes:
        result.append({
            'id': note.id,
            'chart_id': note.chart_id,
            'x_value': note.x_value,
            'y_value': note.y_value,
            'content': note.content
        })
    return jsonify(result)

@app.route('/api/floating_notes', methods=['POST'])
@login_required
@dept_required(['Farm', 'Admin'])
def create_floating_note():
    data = request.json
    try:
        new_note = FloatingNote(
            flock_id=data['flock_id'],
            chart_id=data['chart_id'],
            x_value=data['x_value'],
            y_value=float(data['y_value']),
            content=data['content']
        )
        db.session.add(new_note)
        safe_commit()
        return jsonify({'success': True, 'id': new_note.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/floating_notes/<int:note_id>', methods=['DELETE'])
@login_required
@dept_required(['Farm', 'Admin'])
def delete_floating_note(note_id):
    try:
        note = FloatingNote.query.get_or_404(note_id)
        db.session.delete(note)
        safe_commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/daily_log/trend')
@login_required
def api_daily_log_trend():
    flock_id = request.args.get('flock_id', type=int)
    end_date_str = request.args.get('date')
    if not flock_id or not end_date_str:
        return jsonify({'error': 'Missing parameters'}), 400

    try:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400

    start_date = end_date - timedelta(days=70) # Fetch up to 10 weeks

    flock = Flock.query.get_or_404(flock_id)

    logs = DailyLog.query.filter(
        DailyLog.flock_id == flock_id,
        DailyLog.date >= start_date,
        DailyLog.date <= end_date
    ).order_by(DailyLog.date.asc()).all()

    gs = GlobalStandard.query.first()
    enriched = enrich_flock_data(flock, logs)

    cum_mort_m_pct = 0
    cum_mort_f_pct = 0
    if enriched:
        # Get phase-aware cumulative mortality from the last calculated day
        cum_mort_m_pct = enriched[-1].get('mortality_cum_male_pct', 0)
        cum_mort_f_pct = enriched[-1].get('mortality_cum_female_pct', 0)

    # Fetch Standards
    all_standards = GlobalStandard.query.all()
    prod_std_map = {getattr(s, "age_weeks", getattr(s, "production_week", None)): s for s in all_standards if getattr(s, "age_weeks", getattr(s, "production_week", None)) is not None}

    # Attach Standards
    for d in enriched:
        prod_std = None
        if d.get('production_week'):
            prod_std = prod_std_map.get(d['production_week'])

        d['std_egg_prod'] = (prod_std.std_egg_prod if prod_std and prod_std.std_egg_prod is not None else 0.0)
        d['std_hatching_egg_pct'] = (prod_std.std_hatching_egg_pct if prod_std and prod_std.std_hatching_egg_pct is not None else 0.0)

    trend_data = []
    water_trend_data = []
    end_day_log = None

    # Track weekly stats
    from metrics import aggregate_weekly_metrics
    weekly_stats = aggregate_weekly_metrics(enriched)

    for entry in enriched:
        log = entry['log']
        item = {
            'date': log.date.strftime('%Y-%m-%d'),
            'mort_m_pct': entry.get('mortality_male_pct', 0.0),
            'mort_f_pct': entry.get('mortality_female_pct', 0.0),
            'egg_prod_pct': entry.get('egg_prod_pct', 0.0),
            'std_egg_prod': entry.get('std_egg_prod', 0.0),
            'hatching_eggs': entry.get('hatch_eggs', 0),
            'hatching_egg_pct': entry.get('hatch_egg_pct', 0.0),
            'std_hatching_pct': entry.get('std_hatching_egg_pct', 0.0),
            'cull_jumbo_pct': entry.get('cull_eggs_jumbo_pct', 0.0),
            'cull_small_pct': entry.get('cull_eggs_small_pct', 0.0),
            'cull_abnormal_pct': entry.get('cull_eggs_abnormal_pct', 0.0),
            'cull_crack_pct': entry.get('cull_eggs_crack_pct', 0.0),
            'water_per_bird': entry.get('water_per_bird', 0.0),
            'water_feed_ratio': entry.get('water_feed_ratio', 0.0),
            'flushing': log.flushing,
            'is_target_day': log.date == end_date
        }

        days_diff = (end_date - log.date).days
        if days_diff <= 7 and days_diff >= 0: # Last 7 days including today
            trend_data.append(item)

        if days_diff <= 8 and days_diff >= 1: # Last 7 days ending yesterday
            water_trend_data.append(item)

        if log.date == end_date:
            end_day_log = entry

    # Prepare weekly BW data
    weekly_trend = []
    for w in weekly_stats[-10:]: # Get up to the last 10 weeks
        w_log = w.get('log')
        w_item = {
            'week': w.get('week', 0),
            'bw_male': w.get('body_weight_male', 0.0) or None,
            'bw_female': w.get('body_weight_female', 0.0) or None,
            'uniformity_male': w.get('uniformity_male', 0.0) or None,
            'uniformity_female': w.get('uniformity_female', 0.0) or None,
            'std_bw_male': None,
            'std_bw_female': None,
            'selection_done': any(e['log'].selection_done for e in enriched if e.get('week') == w.get('week')),
            'spiking': any(e['log'].spiking for e in enriched if e.get('week') == w.get('week'))
        }
        # Add std
        std_w = Standard.query.filter_by(week=w.get('week', 0)).first()
        if std_w:
            w_item['std_bw_male'] = std_w.std_bw_male or None
            w_item['std_bw_female'] = std_w.std_bw_female or None
        weekly_trend.append(w_item)

    # If no data for the exact target date, we return empty data flag but not an error
    if not end_day_log:
        return jsonify({
            'empty': True,
            'house_name': flock.house.name,
            'date': end_date.strftime('%d-%m-%Y')
        })

    log = end_day_log['log']

    notes = [n.description for n in log.clinical_notes_list] if log.clinical_notes_list else []
    notes_str = ", ".join(notes) if notes else "None"

    medications_used = db.session.query(Medication).filter(
        Medication.flock_id == flock_id,
        Medication.start_date <= log.date,
        db.or_(Medication.end_date == None, Medication.end_date >= log.date)
    ).all()
    meds_str = ", ".join([m.drug_name for m in medications_used]) if medications_used else "None"

    # Get Vaccinations for the day
    vaccines_used = Vaccine.query.filter_by(flock_id=flock_id, actual_date=log.date).all()
    vaccines_str = ", ".join([v.vaccine_name for v in vaccines_used]) if vaccines_used else ""

    stock_m = end_day_log.get('stock_male_prod_end', 0) + end_day_log.get('stock_male_hosp_end', 0)
    stock_f = end_day_log.get('stock_female_prod_end', 0) + end_day_log.get('stock_female_hosp_end', 0)
    total_feed_kg = ((log.feed_male_gp_bird * stock_m) + (log.feed_female_gp_bird * stock_f)) / 1000

    # Get proper standard egg weight for the current week
    std_obj = Standard.query.filter_by(week=end_day_log.get('week', 0)).first()
    std_egg_weight = std_obj.std_egg_weight if std_obj and std_obj.std_egg_weight else 0.0

    # Calculate Lighting and Feed Cleanup manually as they are view-specific in other parts of app.py
    lighting_hours = 0.0
    if log.light_on_time and log.light_off_time:
        try:
            t1 = datetime.strptime(log.light_on_time, '%H:%M')
            t2 = datetime.strptime(log.light_off_time, '%H:%M')
            diff = (t2 - t1).total_seconds() / 3600
            if diff < 0: diff += 24
            lighting_hours = round(diff, 1)
        except: pass

    feed_cleanup_hours = 0.0
    if log.feed_cleanup_start and log.feed_cleanup_end:
        try:
            from app import calculate_feed_cleanup_duration
            duration = calculate_feed_cleanup_duration(log.feed_cleanup_start, log.feed_cleanup_end)
            if duration: feed_cleanup_hours = round(duration / 60.0, 1)
        except: pass

    notes_str = log.remarks if log.remarks else "None"

    report_info = {
        'empty': False,
        'house_name': flock.house.name,
        'age_week': end_day_log.get('week', 0),
        'phase': getattr(flock, 'calculated_phase', flock.phase),
        'date': end_date.strftime('%d-%m-%Y'),
        'lighting_hours': lighting_hours,
        'feed_cleanup_hours': feed_cleanup_hours,
        'stock_m': end_day_log.get('stock_male_prod_end', 0) + end_day_log.get('stock_male_hosp_end', 0),
        'stock_f': end_day_log.get('stock_female_prod_end', 0) + end_day_log.get('stock_female_hosp_end', 0),
        'cum_mort_m_pct': round(cum_mort_m_pct, 2),
        'cum_mort_f_pct': round(cum_mort_f_pct, 2),
        'egg_weight': log.egg_weight or 0.0,
        'std_egg_weight': std_egg_weight,
        'feed_m': log.feed_male_gp_bird,
        'feed_f': log.feed_female_gp_bird,
        'total_feed_kg': round(total_feed_kg, 2),
        'medication': meds_str,
        'vaccination': vaccines_str,
        'notes': notes_str,
        'trend': trend_data,
        'water_trend': water_trend_data,
        'weekly_trend': weekly_trend
    }

    return jsonify(report_info)


import base64
from werkzeug.utils import secure_filename

@app.route('/api/reports/backup', methods=['POST'])
@login_required
def backup_report_image():
    data = request.json
    if not data or 'image' not in data or 'date' not in data or 'house' not in data or 'age' not in data:
        return jsonify({'error': 'Missing data'}), 400

    image_data = data['image']
    if ',' in image_data:
        image_data = image_data.split(',')[1]

    date_str = data['date'] # YYYY-MM-DD
    house_name = data['house']
    age_week = data['age']

    filename = f"{date_str}_{secure_filename(house_name)}_W{age_week}.jpg"

    reports_dir = os.path.join(app.root_path, 'static', 'reports')
    if not os.path.exists(reports_dir):
        os.makedirs(reports_dir)

    filepath = os.path.join(reports_dir, filename)

    try:
        with open(filepath, "wb") as fh:
            fh.write(base64.b64decode(image_data))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    try:
        current_time = datetime.now()
        for f in os.listdir(reports_dir):
            f_path = os.path.join(reports_dir, f)
            if os.path.isfile(f_path):
                mtime = datetime.fromtimestamp(os.path.getmtime(f_path))
                if (current_time - mtime).days > 7:
                    os.remove(f_path)
    except Exception as e:
        pass

    return jsonify({'success': True, 'path': f'/static/reports/{filename}'})


# Ensure tables are created on startup if they don't exist
with app.app_context():
    try:
        db.create_all()
        init_ui_elements(commit=True)
    except Exception as e:
        app.logger.warning(f"Error during db.create_all() or init_ui_elements(): {e}")



@app.route('/api/offline_snapshot')
@login_required
def offline_snapshot():
    if not current_user.id:
        return jsonify({'error': 'Unauthorized'}), 401

    user_dept = current_user.dept
    is_admin = current_user.role == 'Admin'
    user_role = current_user.role

    # Restrict to allowed departments if not Admin/Management
    query = Flock.query.filter_by(status='Active')
    if not is_admin and user_role != 'Management':
        if user_dept == 'Farm':
            # This is a bit simplified, usually we might restrict by house or just Farm
            pass
        elif user_dept == 'Hatchery':
            pass

    active_flocks = query.all()

    from datetime import date, timedelta
    twelve_months_ago = date.today() - timedelta(days=365)

    snapshot_data = []
    from metrics import enrich_flock_data, aggregate_weekly_metrics

    for f in active_flocks:
        # Get logs from last 12 months
        logs = [log for log in f.logs if log.date and log.date >= twelve_months_ago]
        logs.sort(key=lambda x: x.date)

        # Enrich the flock data to get phases and dynamic properties
        hatch_recs = [] # Skip hatch records for this snapshot to save bandwidth unless needed
        enriched_data = enrich_flock_data(f, logs)

        daily_logs_data = []
        recent_detailed_logs = []

        # We need the last 14 days of detailed logs
        from datetime import date, timedelta
        fourteen_days_ago = date.today() - timedelta(days=14)

        for d in enriched_data:
            if d.get('date'):
                date_str = d.get('date').strftime('%Y-%m-%d')

                # Basic summary for dashboard
                daily_logs_data.append({
                    'date': date_str,
                    'age_week_day': d.get('age_week_day'),
                    'mortality_cum_female_pct': d.get('mortality_cum_female_pct'),
                    'eggs_production_pct': d.get('eggs_production_pct'),
                    'feed_female_gp_bird': d.get('feed_female_gp_bird'),
                    'calculated_phase': d.get('calculated_phase'),
                    'stock_female_end': d.get('stock_female_end'),
                    'stock_male_end': d.get('stock_male_end')
                })

                # Full details for the last 14 days
                if d.get('date') >= fourteen_days_ago:
                    log_obj = d.get('log')
                    if log_obj:
                        recent_detailed_logs.append({
                            'date': date_str,
                            'age_week_day': d.get('age_week_day'),
                            'calculated_phase': d.get('calculated_phase'),
                            'mortality_male': log_obj.mortality_male,
                            'mortality_female': log_obj.mortality_female,
                            'culls_male': log_obj.culls_male,
                            'culls_female': log_obj.culls_female,
                            'feed_male_gp_bird': log_obj.feed_male_gp_bird,
                            'feed_female_gp_bird': log_obj.feed_female_gp_bird,
                            'eggs_collected': log_obj.eggs_collected,
                            'egg_weight': log_obj.egg_weight,
                            'water_intake_calculated': log_obj.water_intake_calculated,
                            'body_weight_male': log_obj.body_weight_male,
                            'body_weight_female': log_obj.body_weight_female,
                            'uniformity_male': log_obj.uniformity_male,
                            'uniformity_female': log_obj.uniformity_female,
                            'mortality_male_pct': d.get('mortality_male_pct', 0),
                            'mortality_female_pct': d.get('mortality_female_pct', 0),
                            'mortality_cum_male_pct': d.get('mortality_cum_male_pct', 0),
                            'mortality_cum_female_pct': d.get('mortality_cum_female_pct', 0),
                            'egg_prod_pct': d.get('egg_prod_pct', 0),
                            'water_per_bird': d.get('water_per_bird', 0),
                            'stock_male_start': d.get('stock_male_start', 0),
                            'stock_female_start': d.get('stock_female_start', 0)
                        })

        weekly_averages = aggregate_weekly_metrics(enriched_data)
        weekly_data = []
        for w in weekly_averages:
            weekly_data.append({
                'age_weeks': w.get('age_weeks'),
                'production_week': w.get('production_week'),
                'avg_egg_production_pct': w.get('avg_egg_production_pct'),
                'mortality_f_weekly_pct': w.get('mortality_f_weekly_pct'),
                'avg_feed_f': w.get('avg_feed_f'),
                'avg_feed_m': w.get('avg_feed_m'),
            })

        snapshot_data.append({
            'flock_id': f.id,
            'house_name': f.house.name if f.house else f.name,
            'farm_name': f.farm.name if f.farm else 'N/A',
            'status': f.status,
            'calculated_phase': getattr(f, 'calculated_phase', 'Unknown'),
            'intake_date': f.intake_date.strftime('%Y-%m-%d') if f.intake_date else None,
            'intake_male': f.intake_male,
            'intake_female': f.intake_female,
            'doa_male': f.doa_male,
            'doa_female': f.doa_female,
            'daily_logs': daily_logs_data,
            'recent_detailed_logs': recent_detailed_logs,
            'weekly_averages': weekly_data
        })

    from datetime import datetime
    return jsonify({
        'timestamp': datetime.now().isoformat(),
        'flocks': snapshot_data
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
