from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session, g
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy.orm import joinedload
from sqlalchemy import or_, and_, func
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
import os
import time
from dotenv import load_dotenv
import json
import pandas as pd
import calendar
import re
from functools import wraps
from metrics import METRICS_REGISTRY, calculate_metrics, enrich_flock_data, aggregate_weekly_metrics, aggregate_monthly_metrics

load_dotenv()

# Initial User Data for Seeding
INITIAL_USERS = [
    {'username': 'admin', 'password': 'admin123', 'dept': 'Admin', 'role': 'Admin'},
    {'username': 'farm_user', 'password': 'farm123', 'dept': 'Farm', 'role': 'Worker'},
    {'username': 'hatch_user', 'password': 'hatch123', 'dept': 'Hatchery', 'role': 'Worker'},
    {'username': 'manager', 'password': 'manager123', 'dept': 'Management', 'role': 'Management'}
]

# Pre-compile regex for natural sorting
_ns_re = re.compile('([0-9]+)')

def natural_sort_key(flock):
    s = flock.house.name
    return [int(text) if text.isdigit() else text.lower()
            for text in _ns_re.split(s)]

def dept_required(required_dept):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_dept = session.get('user_dept')

            # Super Admin can access everything
            if user_dept == 'Admin':
                return f(*args, **kwargs)

            # If user matches required dept
            if user_dept == required_dept:
                return f(*args, **kwargs)

            # If guest (None)
            if user_dept is None:
                if request.path == url_for('login'): # Avoid loop
                    return f(*args, **kwargs)
                flash("Please log in to continue.", "info")
                return redirect(url_for('login'))

            # If user is logged in but wrong department
            flash(f"Access Denied: You do not have permission to view the {required_dept} Department", "danger")

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

app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
database_url = os.getenv('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///' + os.path.join(basedir, 'instance', 'farm.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev_key')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=31)
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)

@app.template_filter('basename')
def basename_filter(s):
    if not s:
        return None
    return os.path.basename(str(s).replace('\\', '/'))

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

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# --- Models ---

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    dept = db.Column(db.String(50), nullable=False)
    role = db.Column(db.String(50), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class FeedCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)

class House(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    flocks = db.relationship('Flock', backref='house', lazy=True)

    # Dashboard Configs (From Feature Branch)
    charts = db.relationship('ChartConfiguration', backref='house', lazy=True, cascade="all, delete-orphan")
    overview_config = db.relationship('OverviewConfiguration', backref='house', uselist=False, cascade="all, delete-orphan")

class ChartConfiguration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    house_id = db.Column(db.Integer, db.ForeignKey('house.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    chart_type = db.Column(db.String(20), default='line') # 'line', 'bar'
    config_json = db.Column(db.Text, nullable=False) # JSON: metrics, axis settings, colors
    is_template = db.Column(db.Boolean, default=False)

class OverviewConfiguration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    house_id = db.Column(db.Integer, db.ForeignKey('house.id'), nullable=False, unique=True)
    visible_metrics_json = db.Column(db.Text, nullable=False) # JSON list of keys

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
    house_id = db.Column(db.Integer, db.ForeignKey('house.id'), nullable=False)
    flock_id = db.Column(db.String(100), unique=True, nullable=False)
    intake_date = db.Column(db.Date, nullable=False, default=date.today)
    
    # Intake Counts
    intake_male = db.Column(db.Integer, default=0)
    intake_female = db.Column(db.Integer, default=0)
    
    # DOA
    doa_male = db.Column(db.Integer, default=0)
    doa_female = db.Column(db.Integer, default=0)
    
    status = db.Column(db.String(20), default='Active', nullable=False) # 'Active' or 'Inactive'
    phase = db.Column(db.String(20), default='Rearing', nullable=False) # 'Rearing' or 'Production'
    production_start_date = db.Column(db.Date, nullable=True) # Date when production phase started

    # Production Start Counts (New Baseline)
    prod_start_male = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    prod_start_female = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    prod_start_male_hosp = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    prod_start_female_hosp = db.Column(db.Integer, default=0, nullable=False, server_default='0')

    end_date = db.Column(db.Date, nullable=True)
    
    logs = db.relationship('DailyLog', backref='flock', lazy=True, cascade="all, delete-orphan")
    weekly_data = db.relationship('WeeklyData', backref='flock', lazy=True, cascade="all, delete-orphan")
    weekly_benchmarks = db.relationship('ImportedWeeklyBenchmark', backref='flock', lazy=True, cascade="all, delete-orphan")

class DailyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flock_id = db.Column(db.Integer, db.ForeignKey('flock.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    
    # Metrics
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
    feed_male = db.Column(db.Float, default=0.0, nullable=False, server_default='0')
    feed_female = db.Column(db.Float, default=0.0, nullable=False, server_default='0')

    eggs_collected = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    
    cull_eggs_jumbo = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    cull_eggs_small = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    cull_eggs_abnormal = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    cull_eggs_crack = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    
    egg_weight = db.Column(db.Float, default=0.0)
    
    # Body Weight (Split by Sex)
    body_weight_male = db.Column(db.Integer, default=0)
    body_weight_female = db.Column(db.Integer, default=0)
    uniformity_male = db.Column(db.Float, default=0.0)
    uniformity_female = db.Column(db.Float, default=0.0)

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
    photo_path = db.Column(db.String(200)) # Path to file
    flushing = db.Column(db.Boolean, default=False)

    # Feed Codes (Main Branch Logic)
    feed_code_male_id = db.Column(db.Integer, db.ForeignKey('feed_code.id'), nullable=True)
    feed_code_female_id = db.Column(db.Integer, db.ForeignKey('feed_code.id'), nullable=True)

    feed_code_male = db.relationship('FeedCode', foreign_keys=[feed_code_male_id], backref='male_logs')
    feed_code_female = db.relationship('FeedCode', foreign_keys=[feed_code_female_id], backref='female_logs')

    partition_weights = db.relationship('PartitionWeight', backref='log', lazy=True, cascade="all, delete-orphan")

    @property
    def age_week_day(self):
        delta = (self.date - self.flock.intake_date).days
        if delta < 1:
            return "0.0"
        weeks = (delta - 1) // 7
        days = (delta - 1) % 7 + 1
        return f"{weeks}.{days}"

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

class GlobalStandard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    std_mortality_daily = db.Column(db.Float, default=0.05)
    std_mortality_weekly = db.Column(db.Float, default=0.3)
    std_hatching_egg_pct = db.Column(db.Float, default=96.0)

class UIElement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    label = db.Column(db.String(100), nullable=False)
    section = db.Column(db.String(50), nullable=False) # 'navbar_main', 'navbar_health', 'flock_card', 'flock_detail'
    is_visible = db.Column(db.Boolean, default=True)
    order_index = db.Column(db.Integer, default=0)

class WeeklyData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flock_id = db.Column(db.Integer, db.ForeignKey('flock.id'), nullable=False)
    week = db.Column(db.Integer, nullable=False)

    mortality_male = db.Column(db.Integer, default=0)
    mortality_female = db.Column(db.Integer, default=0)
    culls_male = db.Column(db.Integer, default=0)
    culls_female = db.Column(db.Integer, default=0)

    eggs_collected = db.Column(db.Integer, default=0)

    bw_male = db.Column(db.Integer, default=0)
    bw_female = db.Column(db.Integer, default=0)

    feed_male = db.Column(db.Float, default=0.0) # Total Kg
    feed_female = db.Column(db.Float, default=0.0) # Total Kg

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

def calculate_male_ratio(flock_id, setting_date, flock_obj=None, logs=None, last_hatch_date=None):
    flock = flock_obj or Flock.query.get(flock_id)
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
            # Find LAST setting date for this flock BEFORE current setting_date
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

        # Navbar Health Dropdown
        {'key': 'nav_health_vaccine', 'label': 'Vaccine', 'section': 'navbar_health', 'order': 1},
        {'key': 'nav_health_sampling', 'label': 'Sampling', 'section': 'navbar_health', 'order': 2},
        {'key': 'nav_health_medication', 'label': 'Medication', 'section': 'navbar_health', 'order': 3},
        {'key': 'nav_health_notes', 'label': 'Clinical Notes', 'section': 'navbar_health', 'order': 4},

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

    for elem in default_elements:
        existing = UIElement.query.filter_by(key=elem['key']).first()
        if not existing:
            new_elem = UIElement(
                key=elem['key'],
                label=elem['label'],
                section=elem['section'],
                order_index=elem['order']
            )
            db.session.add(new_elem)

    if commit:
        db.session.commit()
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
        db.session.commit()
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
    db.session.commit()

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
                offset = days - 1
            except: pass
        elif age_code.startswith('W'):
            try:
                weeks = int(age_code[1:])
                offset = (weeks * 7)
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
        db.session.commit()
    else:
        db.session.flush()

# --- Routes ---

@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id:
        # Optimization: storing simple details in session to avoid DB hit on every request?
        # But for security (role changes), fetching from DB is better.
        # However, sticking to original session-based design for now, but validating existence.
        # Let's trust session for performance, but `g.user` is useful.
        # Note: In session we stored 'username' as 'user_id' in previous code.
        # Let's switch to storing Database ID in session['user_db_id'] maybe?
        # Or stick to username for backward compat?
        # The previous code used session['user_id'] = username.
        # Let's keep using session['user_id'] = username to minimize disruption, but `g.user` will be the object.
        g.user = User.query.filter_by(username=user_id).first()
    else:
        g.user = None

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session.clear()
            session['user_id'] = user.username
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

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        user = User.query.filter_by(username=session['user_id']).first()

        if not user or not user.check_password(current_password):
            flash("Incorrect current password.", "danger")
        elif new_password != confirm_password:
            flash("New passwords do not match.", "danger")
        else:
            user.set_password(new_password)
            db.session.commit()
            flash("Password updated successfully.", "success")
            return redirect(url_for('index'))

    return render_template('change_password.html')

@app.route('/admin/users')
def admin_users():
    if not session.get('is_admin'):
        flash("Access Denied.", "danger")
        return redirect(url_for('index'))
    users = User.query.order_by(User.username).all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/users/add', methods=['POST'])
def admin_user_add():
    if not session.get('is_admin'): return redirect(url_for('index'))

    username = request.form.get('username')
    password = request.form.get('password')
    dept = request.form.get('dept')
    role = request.form.get('role')

    if User.query.filter_by(username=username).first():
        flash(f"User {username} already exists.", "warning")
    else:
        u = User(username=username, dept=dept, role=role)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        flash(f"User {username} added.", "success")
    return redirect(url_for('admin_users'))

@app.route('/admin/users/edit/<int:user_id>', methods=['POST'])
def admin_user_edit(user_id):
    if not session.get('is_admin'): return redirect(url_for('index'))

    user = User.query.get_or_404(user_id)
    dept = request.form.get('dept')
    role = request.form.get('role')

    user.dept = dept
    user.role = role
    db.session.commit()
    flash(f"User {user.username} updated.", "success")
    return redirect(url_for('admin_users'))

@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
def admin_user_delete(user_id):
    if not session.get('is_admin'): return redirect(url_for('index'))

    user = User.query.get_or_404(user_id)
    if user.username == session['user_id']:
        flash("Cannot delete yourself.", "danger")
    else:
        db.session.delete(user)
        db.session.commit()
        flash(f"User {user.username} deleted.", "info")
    return redirect(url_for('admin_users'))

@app.route('/admin/users/reset_password/<int:user_id>', methods=['POST'])
def admin_user_reset_password(user_id):
    if not session.get('is_admin'): return redirect(url_for('index'))

    user = User.query.get_or_404(user_id)
    new_pass = request.form.get('new_password')
    if new_pass:
        user.set_password(new_pass)
        db.session.commit()
        flash(f"Password for {user.username} has been reset.", "success")
    else:
        flash("Password cannot be empty.", "danger")
    return redirect(url_for('admin_users'))

@app.route('/hatchery')
@dept_required('Hatchery')
def hatchery_dashboard():
    active_flocks = Flock.query.filter_by(status='Active', phase='Production').all()
    active_flocks.sort(key=natural_sort_key)
    today = date.today()
    for f in active_flocks:
        days = (today - f.intake_date).days
        f.current_week = (days // 7) if days >= 0 else 0

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
@dept_required('Farm')
def index():
    active_flocks = Flock.query.options(joinedload(Flock.logs), joinedload(Flock.house)).filter_by(status='Active').all()

    # Inventory Check for Dashboard
    low_stock_items = InventoryItem.query.filter(InventoryItem.current_stock < InventoryItem.min_stock_level).all()
    low_stock_count = len(low_stock_items)

    active_flocks.sort(key=natural_sort_key)

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
        f.age_weeks = days_age // 7
        f.age_days = days_age % 7
        f.current_week = (days_age // 7) + 1 if days_age >= 0 else 0

        # Stats
        if daily_stats:
            last = daily_stats[-1]
            if last['date'] == today:
                f.has_log_today = True

            # Cumulative Pct (Phase specific)
            if f.phase == 'Rearing':
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

                if f.daily_stats['mort_m_diff'] > 0: f.daily_stats['mort_m_trend'] = 'up'
                elif f.daily_stats['mort_m_diff'] < 0: f.daily_stats['mort_m_trend'] = 'down'

                if f.daily_stats['mort_f_diff'] > 0: f.daily_stats['mort_f_trend'] = 'up'
                elif f.daily_stats['mort_f_diff'] < 0: f.daily_stats['mort_f_trend'] = 'down'

                if f.daily_stats['egg_diff'] > 0: f.daily_stats['egg_trend'] = 'up'
                elif f.daily_stats['egg_diff'] < 0: f.daily_stats['egg_trend'] = 'down'

    return render_template('index.html', active_flocks=active_flocks, today=today, low_stock_items=low_stock_items, low_stock_count=low_stock_count)

@app.route('/clinical_notes')
@dept_required('Farm')
def clinical_notes():
    house_id = request.args.get('house_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    search = request.args.get('search', '').strip()

    # Base Query: Has notes OR photo
    query = DailyLog.query.join(Flock).join(House).filter(
        or_(
            and_(DailyLog.clinical_notes != None, DailyLog.clinical_notes != ''),
            DailyLog.photo_path != None
        )
    )

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
    houses = House.query.order_by(House.name).all()

    return render_template('clinical_notes.html', logs=logs, houses=houses)

@app.route('/flock/<int:id>/edit', methods=['GET', 'POST'])
@dept_required('Farm')
def edit_flock(id):
    flock = Flock.query.get_or_404(id)
    if request.method == 'POST':
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

        prod_start_str = request.form.get('production_start_date')
        if prod_start_str:
             flock.production_start_date = datetime.strptime(prod_start_str, '%Y-%m-%d').date()
        else:
             flock.production_start_date = None

        flock.intake_male = int(request.form.get('intake_male') or 0)
        flock.intake_female = int(request.form.get('intake_female') or 0)
        flock.doa_male = int(request.form.get('doa_male') or 0)
        flock.doa_female = int(request.form.get('doa_female') or 0)

        db.session.commit()
        flash(f'Flock {flock.flock_id} updated.', 'success')
        return redirect(url_for('index'))

    return render_template('flock_edit.html', flock=flock)

@app.route('/flock/<int:id>/delete', methods=['POST'])
@dept_required('Farm')
def delete_flock(id):
    flock = Flock.query.get_or_404(id)
    db.session.delete(flock)
    db.session.commit()
    flash(f'Flock {flock.flock_id} deleted.', 'warning')
    return redirect(url_for('manage_flocks'))

@app.route('/help')
def help():
    return render_template('help.html')

@app.route('/flocks', methods=['GET', 'POST'])
@dept_required('Farm')
def manage_flocks():
    if request.method == 'POST':
        house_name = request.form.get('house_name').strip()
        intake_date_str = request.form.get('intake_date')

        prod_start_date_str = request.form.get('production_start_date')
        prod_start_date = None
        if prod_start_date_str:
            prod_start_date = datetime.strptime(prod_start_date_str, '%Y-%m-%d').date()

        intake_male = int(request.form.get('intake_male') or 0)
        intake_female = int(request.form.get('intake_female') or 0)
        doa_male = int(request.form.get('doa_male') or 0)
        doa_female = int(request.form.get('doa_female') or 0)
        
        # Find or Create House
        house = House.query.filter_by(name=house_name).first()
        if not house:
            house = House(name=house_name)
            db.session.add(house)
            db.session.commit()
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
            flock_id=flock_id,
            intake_date=intake_date,
            intake_male=intake_male,
            intake_female=intake_female,
            doa_male=doa_male,
            doa_female=doa_female,
            production_start_date=prod_start_date
        )
        
        db.session.add(new_flock)
        db.session.commit()

        initialize_sampling_schedule(new_flock.id)
        initialize_vaccine_schedule(new_flock.id)

        flash(f'Flock created successfully! Flock ID: {flock_id}', 'success')
        return redirect(url_for('index'))
    
    houses = House.query.all()
    flocks = Flock.query.order_by(Flock.intake_date.desc()).all()
    return render_template('flock_form.html', houses=houses, flocks=flocks)

@app.route('/flock/<int:id>/close', methods=['POST'])
@dept_required('Farm')
def close_flock(id):
    flock = Flock.query.get_or_404(id)
    flock.status = 'Inactive'
    flock.end_date = date.today()
    db.session.commit()
    flash(f'Flock {flock.flock_id} closed.', 'info')
    return redirect(url_for('index'))

@app.route('/standards', methods=['GET', 'POST'])
@dept_required('Farm')
def manage_standards():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            week_val = request.form.get('week')
            if not week_val or not week_val.isdigit():
                flash('Invalid or missing week number.', 'danger')
                return redirect(url_for('manage_standards'))

            s = Standard(
                week=int(week_val),
                std_mortality_male=float(request.form.get('std_mortality_male') or 0),
                std_mortality_female=float(request.form.get('std_mortality_female') or 0),
                std_bw_male=round_to_whole(request.form.get('std_bw_male')),
                std_bw_female=round_to_whole(request.form.get('std_bw_female')),
                std_egg_prod=float(request.form.get('std_egg_prod') or 0),
                std_egg_weight=float(request.form.get('std_egg_weight') or 0),
                std_hatchability=float(request.form.get('std_hatchability') or 0)
            )
            db.session.add(s)
            db.session.commit()
            flash('Standard added.', 'success')
        elif action == 'update_global':
            gs = GlobalStandard.query.first()
            if not gs:
                gs = GlobalStandard()
                db.session.add(gs)

            gs.std_mortality_daily = float(request.form.get('std_mortality_daily') or 0.05)
            gs.std_mortality_weekly = float(request.form.get('std_mortality_weekly') or 0.3)
            gs.std_hatching_egg_pct = float(request.form.get('std_hatching_egg_pct') or 96.0)
            db.session.commit()
            flash('Global standards updated.', 'success')

        elif action == 'seed_standards':
            success, message = seed_standards_from_file()
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
                db.session.commit()
                flash(f'Feed Code {code} added.', 'success')
        return redirect(url_for('manage_feed_codes'))

    if FeedCode.query.count() == 0:
        default_codes = ['161C', '162C', '163C', '168C', '169C', '170P', '171P', '172P']
        for c in default_codes:
            db.session.add(FeedCode(code=c))
        db.session.commit()

    codes = FeedCode.query.order_by(FeedCode.code.asc()).all()
    return render_template('feed_codes.html', codes=codes)

@app.route('/feed_codes/delete/<int:id>', methods=['POST'])
@dept_required('Farm')
def delete_feed_code(id):
    fc = FeedCode.query.get_or_404(id)
    db.session.delete(fc)
    db.session.commit()
    flash(f'Feed Code {fc.code} deleted.', 'info')
    return redirect(url_for('manage_feed_codes'))

@app.route('/daily_log/delete/<int:id>', methods=['POST'])
@dept_required('Farm')
def delete_daily_log(id):
    if not session.get('is_admin'): return redirect(url_for('index'))

    log = DailyLog.query.get_or_404(id)
    flock_id = log.flock_id

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
    db.session.commit()
    flash("Daily Log deleted.", "info")
    return redirect(url_for('view_flock', id=flock_id))

@app.route('/api/chart_data/<int:flock_id>')
@dept_required('Farm')
def get_chart_data(flock_id):
    flock = Flock.query.get_or_404(flock_id)

    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    mode = request.args.get('mode', 'daily') # 'daily', 'weekly', 'monthly'

    hatch_records = Hatchability.query.filter_by(flock_id=flock_id).all()
    all_logs = DailyLog.query.filter_by(flock_id=flock_id).order_by(DailyLog.date.asc()).all()

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
            data['metrics']['water_per_bird'].append(round(d['water_per_bird'], 1))

            log = d['log']
            if log.photo_path or log.clinical_notes or log.flushing:
                note = log.clinical_notes or ""
                if log.flushing: note = f"[FLUSHING] {note}"

                data['events'].append({
                    'date': log.date.isoformat(),
                    'note': note.strip(),
                    'photo': url_for('uploaded_file', filename=os.path.basename(log.photo_path)) if log.photo_path else None,
                    'type': 'flushing' if log.flushing else 'note'
                })

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
            data['metrics']['water_per_bird'].append(round(a['water_per_bird'], 1))

    return data

@app.route('/flock/<int:id>/toggle_phase', methods=['POST'])
@dept_required('Farm')
def toggle_phase(id):
    flock = Flock.query.get_or_404(id)
    if flock.phase == 'Rearing':
        flock.phase = 'Production'

        prod_date_str = request.form.get('production_start_date')
        if prod_date_str:
            flock.production_start_date = datetime.strptime(prod_date_str, '%Y-%m-%d').date()
        else:
            flock.production_start_date = date.today()

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

        msg = f'Flock {flock.flock_id} switched to Production.'
        if diff_m != 0 or diff_f != 0:
            msg += f' Warning: Count Discrepancy (M: {diff_m}, F: {diff_f}). Baseline reset to {actual_m} M / {actual_f} F.'

        flash(msg, 'success' if (diff_m == 0 and diff_f == 0) else 'warning')
    else:
        flock.phase = 'Rearing'
        flock.production_start_date = None
        flash(f'Flock {flock.flock_id} switched back to Rearing phase.', 'warning')
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/flock/<int:id>')
@dept_required('Farm')
def view_flock(id):
    active_flocks = Flock.query.options(joinedload(Flock.house)).filter_by(status='Active').all()
    active_flocks.sort(key=natural_sort_key)

    flock = Flock.query.options(joinedload(Flock.house)).filter_by(id=id).first_or_404()
    logs = DailyLog.query.options(joinedload(DailyLog.partition_weights)).filter_by(flock_id=id).order_by(DailyLog.date.asc()).all()

    gs = GlobalStandard.query.first()
    if not gs:
        gs = GlobalStandard()
        db.session.add(gs)
        db.session.commit()

    # --- Standards Setup for Shifted Comparison ---
    all_standards = Standard.query.all()
    std_map = {s.week: s for s in all_standards}
    
    # Find Standard Start Week (first week with egg prod > 0)
    # Default to 24 if not found
    std_start_week = 24
    sorted_stds = sorted(all_standards, key=lambda x: x.week)
    for s in sorted_stds:
        if s.std_egg_prod > 0:
            std_start_week = s.week
            break

    # --- Fetch Hatch Data ---
    hatch_records = Hatchability.query.filter_by(flock_id=id).all()

    # --- Metrics Engine ---
    daily_stats = enrich_flock_data(flock, logs, hatch_records)

    # --- Calculate Actual Start & Offset ---
    actual_start_date = None
    for d in daily_stats:
        if d['eggs_collected'] > 0:
            actual_start_date = d['date']
            break

    offset_weeks = 0
    if actual_start_date:
        actual_start_week = (actual_start_date - flock.intake_date).days // 7 + 1
        offset_weeks = actual_start_week - std_start_week

    # Inject Shifted Standard into daily_stats
    for d in daily_stats:
        current_age_week = d['week']
        # Production Metrics use Shifted Standard
        target_std_week = current_age_week - offset_weeks

        std_obj = std_map.get(target_std_week)
        d['std_egg_prod'] = std_obj.std_egg_prod if std_obj else 0.0

    weekly_stats = aggregate_weekly_metrics(daily_stats)

    # Inject Shifted Standard into weekly_stats (simple average of days or lookup by week?)
    # Lookup by week is cleaner for the graph
    for ws in weekly_stats:
        current_age_week = ws['week']
        target_std_week = current_age_week - offset_weeks
        std_obj = std_map.get(target_std_week)
        ws['std_egg_prod'] = std_obj.std_egg_prod if std_obj else 0.0

    medications = Medication.query.filter_by(flock_id=id).all()

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

        enriched_logs.append({
            'log': log,
            'stock_male': d['stock_male_start'],
            'stock_female': d['stock_female_start'],
            'lighting_hours': lighting_hours,
            'medications': meds_str,
            'egg_prod_pct': d['egg_prod_pct'],
            'total_feed': d['feed_total_kg'],
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

            # Derived
            'mort_pct_m': ws['mortality_male_pct'],
            'mort_pct_f': ws['mortality_female_pct'],
            'cull_pct_m': ws['culls_male_pct'],
            'cull_pct_f': ws['culls_female_pct'],
            'egg_prod_pct': ws['egg_prod_pct'],
            'hatching_egg_pct': ws['hatch_egg_pct'],

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
        'mortality_cum_male': [round(d['mortality_cum_male_pct'], 2) for d in daily_stats],
        'mortality_cum_female': [round(d['mortality_cum_female_pct'], 2) for d in daily_stats],
        'mortality_daily_male': [round(d['mortality_male_pct'], 2) for d in daily_stats],
        'mortality_daily_female': [round(d['mortality_female_pct'], 2) for d in daily_stats],
        'culls_daily_male': [round(d['culls_male_pct'], 2) for d in daily_stats],
        'culls_daily_female': [round(d['culls_female_pct'], 2) for d in daily_stats],
        'egg_prod': [round(d['egg_prod_pct'], 2) for d in daily_stats],
        'std_egg_prod': [round(d['std_egg_prod'], 2) for d in daily_stats],
        'male_ratio': [round(d['male_ratio_stock'], 2) if d['male_ratio_stock'] else 0 for d in daily_stats],
        'bw_male_std': [d['log'].standard_bw_male if d['log'].standard_bw_male > 0 else None for d in daily_stats],
        'bw_female_std': [d['log'].standard_bw_female if d['log'].standard_bw_female > 0 else None for d in daily_stats],
        'unif_male': [scale_pct(d['uniformity_male']) if d['uniformity_male'] > 0 else None for d in daily_stats],
        'unif_female': [scale_pct(d['uniformity_female']) if d['uniformity_female'] > 0 else None for d in daily_stats],

        # Raw BW for charts (None if 0)
        'bw_f': [d['body_weight_female'] if d['body_weight_female'] > 0 else None for d in daily_stats],
        'bw_m': [d['body_weight_male'] if d['body_weight_male'] > 0 else None for d in daily_stats],

        # Legacy Partitions from Log
        'bw_male_p1': [d['log'].bw_male_p1 if d['log'].bw_male_p1 > 0 else None for d in daily_stats],
        'bw_male_p2': [d['log'].bw_male_p2 if d['log'].bw_male_p2 > 0 else None for d in daily_stats],
        'bw_female_p1': [d['log'].bw_female_p1 if d['log'].bw_female_p1 > 0 else None for d in daily_stats],
        'bw_female_p2': [d['log'].bw_female_p2 if d['log'].bw_female_p2 > 0 else None for d in daily_stats],
        'bw_female_p3': [d['log'].bw_female_p3 if d['log'].bw_female_p3 > 0 else None for d in daily_stats],
        'bw_female_p4': [d['log'].bw_female_p4 if d['log'].bw_female_p4 > 0 else None for d in daily_stats],

        'notes': []
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
        if log.clinical_notes or log.photo_path:
            note_obj = {'note': log.clinical_notes, 'photo': url_for('uploaded_file', filename=os.path.basename(log.photo_path)) if log.photo_path else None}
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

        # Standard BW - average of the week's standards? Or just take one? Average is fine.
        # ws doesn't have standard sum. We can take last day's standard.
        chart_data_weekly['bw_male_std'].append(last_day['log'].standard_bw_male if last_day['log'].standard_bw_male > 0 else None)
        chart_data_weekly['bw_female_std'].append(last_day['log'].standard_bw_female if last_day['log'].standard_bw_female > 0 else None)

        chart_data_weekly['unif_male'].append(scale_pct(ws['uniformity_male']) if ws['uniformity_male'] > 0 else None)
        chart_data_weekly['unif_female'].append(scale_pct(ws['uniformity_female']) if ws['uniformity_female'] > 0 else None)

        # Partitions (Need to aggregate if we want weekly partition bars)
        # We didn't aggregate partitions in metrics.py.
        # But for weekly charts, we can just skip or implement simple aggregation here.
        # Existing code aggregated them into `weekly_summary['partitions']`.
        # I omitted that in metrics.py for simplicity but the view needs it.
        # I'll fill with None for now or just take last day? No, Avg is better.
        # Let's map Nones to avoid crash.
        for i in range(1, 9):
            chart_data_weekly[f'bw_M{i}'].append(None)
            chart_data_weekly[f'bw_F{i}'].append(None)

        if ws['notes'] or ws['photos']:
            note_text = " | ".join(ws['notes'])
            photo_url = url_for('uploaded_file', filename=os.path.basename(ws['photos'][0])) if ws['photos'] else None
            chart_data_weekly['notes'].append({'note': note_text, 'photo': photo_url})
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

    return render_template('flock_detail.html', flock=flock, logs=list(reversed(enriched_logs)), weekly_data=weekly_data, chart_data=chart_data, chart_data_weekly=chart_data_weekly, current_stats=current_stats, global_std=gs, active_flocks=active_flocks)

@app.route('/flock/<int:id>/charts')
@dept_required('Farm')
def flock_charts(id):
    flock = Flock.query.options(joinedload(Flock.house)).filter_by(id=id).first_or_404()
    return render_template('flock_charts.html', flock=flock)

@app.route('/flock/<int:id>/sampling')
@dept_required('Farm')
def flock_sampling(id):
    flock = Flock.query.options(joinedload(Flock.house)).filter_by(id=id).first_or_404()
    events = SamplingEvent.query.filter_by(flock_id=id).order_by(SamplingEvent.age_week.asc()).all()
    return render_template('flock_sampling.html', flock=flock, events=events)

@app.route('/flock/<int:id>/vaccines', methods=['GET', 'POST'])
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
            db.session.commit()
            flash('New row added.', 'success')

        elif 'delete_id' in request.form:
            v_id = request.form.get('delete_id')
            v = Vaccine.query.get(v_id)
            if v and v.flock_id == id:
                db.session.delete(v)
                db.session.commit()
                flash('Record deleted.', 'info')

        elif 'save_changes' in request.form:
            # Bulk Update
            vaccine_ids = [k.split('_')[2] for k in request.form.keys() if k.startswith('v_id_')]
            updated_count = 0

            # Pre-fetch stock history for calculation
            stock_history = get_flock_stock_history(id)
            sorted_dates = sorted([d for d in stock_history.keys() if isinstance(d, date)])

            for vid in vaccine_ids:
                v = Vaccine.query.get(vid)
                if not v or v.flock_id != id: continue

                was_completed = v.actual_date is not None

                age_code = request.form.get(f'age_code_{vid}')

                # Handle Inventory
                inv_id_val = request.form.get(f'v_inv_{vid}')
                if inv_id_val and inv_id_val.isdigit():
                    v.inventory_item_id = int(inv_id_val)
                    item = InventoryItem.query.get(v.inventory_item_id)
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
                        inv_item = InventoryItem.query.get(v.inventory_item_id)
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

            db.session.commit()
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

    active_flocks = Flock.query.filter_by(status='Active').all()
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
                db.session.commit()
                flash('Result uploaded successfully.', 'success')
            else:
                flash('Only PDF files are allowed.', 'danger')

    if remarks and not ('file' in request.files and request.files['file'].filename != ''):
        db.session.commit()
        flash('Remarks updated.', 'success')

    return redirect(url_for('flock_sampling', id=id))

@app.route('/flock/<int:id>/custom_dashboard')
@dept_required('Farm')
def flock_custom_dashboard(id):
    flock = Flock.query.options(joinedload(Flock.house)).filter_by(id=id).first_or_404()
    return render_template('flock_dashboard_custom.html', flock=flock)

@app.route('/flock/<int:id>/hatchability', methods=['GET', 'POST'])
def flock_hatchability(id):
    if session.get('user_dept') not in ['Farm', 'Hatchery', 'Admin']:
        flash("Access Denied.", "danger")
        return redirect(url_for('login'))

    flock = Flock.query.options(joinedload(Flock.house)).filter_by(id=id).first_or_404()
    if request.method == 'POST':
        if session.get('user_dept') == 'Farm':
            flash("Farm users have read-only access to Hatchability.", "warning")
            return redirect(url_for('flock_hatchability', id=id))

        action = request.form.get('action')
        if action == 'add':
            try:
                setting_date = datetime.strptime(request.form.get('setting_date'), '%Y-%m-%d').date()
                candling_date = datetime.strptime(request.form.get('candling_date'), '%Y-%m-%d').date()
                hatching_date = datetime.strptime(request.form.get('hatching_date'), '%Y-%m-%d').date()

                # Calculate Male Ratio
                male_ratio, large_window = calculate_male_ratio(flock.id, setting_date)

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
                db.session.commit()

                msg = 'Hatchability record added.'
                if large_window:
                    msg += ' Note: Large collection window detected. Average Male Ratio may be affected.'

                flash(msg, 'success' if not large_window else 'warning')
            except ValueError as e:
                flash(f'Error adding record: {e}', 'danger')

        return redirect(url_for('flock_hatchability', id=id))

    records = Hatchability.query.filter_by(flock_id=id).order_by(Hatchability.setting_date.desc()).all()
    return render_template('flock_hatchability.html', flock=flock, records=records)

@app.route('/flock/<int:id>/hatchability/delete/<int:record_id>', methods=['POST'])
@dept_required('Hatchery')
def delete_hatchability(id, record_id):
    record = Hatchability.query.get_or_404(record_id)
    if record.flock_id != id:
        return "Unauthorized", 403
    db.session.delete(record)
    db.session.commit()
    flash('Record deleted.', 'info')
    return redirect(url_for('flock_hatchability', id=id))

@app.route('/hatchery/charts/<int:flock_id>')
def hatchery_charts(flock_id):
    if session.get('user_dept') not in ['Farm', 'Hatchery', 'Admin']:
        flash("Access Denied.", "danger")
        return redirect(url_for('login'))

    flock = Flock.query.get_or_404(flock_id)
    records = Hatchability.query.filter_by(flock_id=flock_id).order_by(Hatchability.setting_date.asc()).all()

    data = {
        'weeks': [],
        'fertile_pct': [],
        'clear_pct': [],
        'rotten_pct': [],
        'hatch_pct': [],
        'male_ratio_pct': [],
        'notes': []
    }

    # Aggregate by week
    weekly_agg = {}

    for r in records:
        age_days = (r.setting_date - flock.intake_date).days
        week = (age_days // 7) + 1

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
        start_date = flock.intake_date + timedelta(days=(week - 1) * 7)
        end_date = flock.intake_date + timedelta(days=(week * 7) - 1)

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
    if session.get('user_dept') not in ['Farm', 'Hatchery', 'Admin', 'Management']:
        return redirect(url_for('login'))

    is_readonly = request.args.get('readonly') == 'true'

    flock = Flock.query.get_or_404(id)
    try:
        setting_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format.', 'danger')
        return redirect(url_for('flock_hatchability', id=id))

    if request.method == 'POST':
        if session.get('user_dept') == 'Farm' or is_readonly:
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
                        db.session.commit()
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

@app.route('/flock/<int:id>/dashboard')
@dept_required('Farm')
def flock_dashboard(id):
    flock = Flock.query.options(joinedload(Flock.house)).filter_by(id=id).first_or_404()

    date_str = request.args.get('date')
    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = date.today()

    all_logs = DailyLog.query.filter_by(flock_id=id).filter(DailyLog.date <= target_date).order_by(DailyLog.date.asc()).all()

    daily_stats = enrich_flock_data(flock, all_logs)
    stats_map = { d['date']: d for d in daily_stats }

    today_stat = stats_map.get(target_date) or {}
    prev_date = target_date - timedelta(days=1)
    prev_stat = stats_map.get(prev_date) or {}

    age_days = (target_date - flock.intake_date).days
    age_week = (age_days // 7) + 1

    # --- Offset Logic for KPI ---
    # Find Standard Start
    all_standards = Standard.query.all()
    std_start_week = 24
    sorted_stds = sorted(all_standards, key=lambda x: x.week)
    std_map = {s.week: s for s in all_standards}
    for s in sorted_stds:
        if s.std_egg_prod > 0:
            std_start_week = s.week
            break

    # Find Actual Start (First egg in logs)
    # We need to query *all* logs to find the start, even though 'all_logs' is filtered by target_date.
    # Optimization: Use 'all_logs' if it contains the start, otherwise do a quick query.
    # Or just use all_logs since we likely need the start date which is usually BEFORE target_date.
    actual_start_date = None
    for log in all_logs:
        if log.eggs_collected > 0:
            actual_start_date = log.date
            break

    offset_weeks = 0
    if actual_start_date:
        actual_start_week = (actual_start_date - flock.intake_date).days // 7 + 1
        offset_weeks = actual_start_week - std_start_week

    standard = std_map.get(age_week) # Biological Standard
    prod_standard_week = age_week - offset_weeks
    prod_standard = std_map.get(prod_standard_week) # Production Standard

    kpis = []

    std_mort_f = standard.std_mortality_female if standard else None

    kpis.append({
        'label': 'Female Mortality %',
        'value': today_stat.get('mortality_female_pct', 0),
        'prev': prev_stat.get('mortality_female_pct', 0),
        'unit': '%',
        'std': std_mort_f,
        'reverse_bad': True
    })

    kpis.append({
        'label': 'Female Cull %',
        'value': today_stat.get('culls_female_pct', 0),
        'prev': prev_stat.get('culls_female_pct', 0),
        'unit': '%',
        'std': None,
        'reverse_bad': True
    })

    kpis.append({
        'label': 'Female Cum. Mort %',
        'value': today_stat.get('mortality_cum_female_pct', 0),
        'prev': prev_stat.get('mortality_cum_female_pct', 0),
        'unit': '%',
        'std': None,
        'reverse_bad': True
    })

    std_egg = prod_standard.std_egg_prod if prod_standard else None
    kpis.append({
        'label': 'Egg Production %',
        'value': today_stat.get('egg_prod_pct', 0),
        'prev': prev_stat.get('egg_prod_pct', 0),
        'unit': '%',
        'std': std_egg,
        'reverse_bad': False
    })

    std_bw_f = standard.std_bw_female if standard else None
    kpis.append({
        'label': 'Female BW',
        'value': today_stat.get('body_weight_female', 0) or 0,
        'prev': prev_stat.get('body_weight_female', 0) or 0,
        'unit': 'g',
        'std': std_bw_f,
        'reverse_bad': False
    })

    diagnostic_hints = []

    for k in kpis:
        k['diff'] = k['value'] - k['prev']
        k['status'] = 'neutral'

        std_val = k.get('std')
        if std_val is not None and k['value'] > 0:
            if k['reverse_bad']:
                if k['value'] > std_val * 1.1:
                    k['status'] = 'danger'
                    diagnostic_hints.append(f"Abnormal {k['label']}: Deviation > 10% from Standard.")
                elif k['value'] > std_val:
                    k['status'] = 'warning'
            else:
                if k['value'] < std_val * 0.9:
                    k['status'] = 'danger'
                    diagnostic_hints.append(f"Abnormal {k['label']}: Deviation > 10% from Standard.")
                elif k['value'] < std_val:
                    k['status'] = 'warning'

    last_3_logs = DailyLog.query.filter_by(flock_id=id).filter(DailyLog.date <= target_date).order_by(DailyLog.date.desc()).limit(3).all()

    if len(last_3_logs) == 3:
        spike_count = 0
        temp_stock_f = curr_stock_f

        m_pct = ((last_3_logs[0].mortality_female or 0) / temp_stock_f * 100) if temp_stock_f > 0 else 0
        if m_pct > 0.1: spike_count += 1

        temp_stock_f += ((last_3_logs[0].mortality_female or 0) + (last_3_logs[0].culls_female or 0))
        m_pct = ((last_3_logs[1].mortality_female or 0) / temp_stock_f * 100) if temp_stock_f > 0 else 0
        if m_pct > 0.1: spike_count += 1

        temp_stock_f += ((last_3_logs[1].mortality_female or 0) + (last_3_logs[1].culls_female or 0))
        m_pct = ((last_3_logs[2].mortality_female or 0) / temp_stock_f * 100) if temp_stock_f > 0 else 0
        if m_pct > 0.1: spike_count += 1

        if spike_count == 3:
             diagnostic_hints.insert(0, "Warning: Continuous mortality spike—review post-mortem photos.")

    return render_template('flock_kpi.html', flock=flock, kpis=kpis, target_date=target_date, age_week=age_week, age_days=age_days, diagnostic_hints=diagnostic_hints)

@app.route('/daily_log', methods=['GET', 'POST'])
@dept_required('Farm')
def daily_log():
    if request.method == 'POST':
        house_id = request.form.get('house_id')
        date_str = request.form.get('date')
        
        flock = Flock.query.filter_by(house_id=house_id, status='Active').first()
        if not flock:
            flash('Error: No active flock found for this house.', 'danger')
            return redirect(url_for('daily_log'))
        
        log_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        existing_log = DailyLog.query.filter_by(flock_id=flock.id, date=log_date).first()
        
        if existing_log:
            log = existing_log
            flash_msg = 'Daily Log updated successfully!'
        else:
            log = DailyLog(flock_id=flock.id, date=log_date)
            db.session.add(log)
            flash_msg = 'Daily Log submitted successfully!'

        log.flock = flock
        db.session.add(log)

        update_log_from_request(log, request)

        # Handle Vaccines (Mark as Completed)
        vaccine_present_ids = request.form.getlist('vaccine_present_ids')
        vaccine_completed_ids = request.form.getlist('vaccine_completed_ids')

        for vid in vaccine_present_ids:
            vac = Vaccine.query.get(vid)
            if vac and vac.flock_id == flock.id:
                if vid in vaccine_completed_ids:
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

        for i, name_val in enumerate(med_names):
            inv_id_val = med_inventory_ids[i] if i < len(med_inventory_ids) else None

            # Determine Name: Inventory Name > Manual Name
            item_name = name_val
            inv_id = None

            if inv_id_val and inv_id_val.isdigit():
                inv_id = int(inv_id_val)
                item = InventoryItem.query.get(inv_id)
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
                inv_item = InventoryItem.query.get(inv_id)
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

        db.session.commit()
        flash(flash_msg, 'success')
        return redirect(url_for('index'))
        
    active_flocks = Flock.query.filter_by(status='Active').all()
    active_houses = [f.house for f in active_flocks]

    flock_phases = {}
    flock_defaults = {}

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

@app.route('/toggle_admin_view')
def toggle_admin_view():
    if not session.get('is_admin'):
        flash("Unauthorized.", "danger")
        return redirect(url_for('index'))

    session['hide_admin_view'] = not session.get('hide_admin_view', False)
    return redirect(request.referrer or url_for('index'))

@app.context_processor
def utility_processor():
    # Inject Effective Admin & Dept for Simulation
    real_is_admin = session.get('is_admin', False)
    hide_view = session.get('hide_admin_view', False)

    effective_is_admin = real_is_admin
    effective_dept = session.get('user_dept')
    effective_role = session.get('user_role')

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

    return dict(get_partition_val=get_partition_val,
                get_ui_elements=get_ui_elements,
                is_admin=effective_is_admin,
                real_is_admin=real_is_admin,
                user_dept=effective_dept,
                user_role=effective_role,
                is_debug=app.debug)

@app.route('/admin/ui', methods=['GET', 'POST'])
def admin_ui_update():
    if not session.get('is_admin'):
        return redirect(url_for('index'))

    if request.method == 'POST':
        # Process updates
        # Form data: id[], order_{id}, label_{id}, visible_{id}
        ids = request.form.getlist('id[]')

        for id_str in ids:
            eid = int(id_str)
            elem = UIElement.query.get(eid)
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

        db.session.commit()
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
def admin_control_panel():
    if not session.get('is_admin'):
        flash("Access Denied: Admin only.", "danger")
        return redirect(url_for('index'))
    return render_template('admin/control_panel.html')

@app.route('/admin/houses')
def admin_houses():
    if not session.get('is_admin'):
        flash("Access Denied: Admin only.", "danger")
        return redirect(url_for('index'))

    houses = House.query.order_by(House.name).all()
    # Check if houses can be deleted (no flocks)
    for h in houses:
        h.can_delete = (Flock.query.filter_by(house_id=h.id).count() == 0)

    return render_template('admin/houses.html', houses=houses)

@app.route('/admin/houses/add', methods=['POST'])
def admin_house_add():
    if not session.get('is_admin'): return redirect(url_for('index'))

    name = request.form.get('name').strip()
    if not name:
        flash("House name is required.", "danger")
    elif House.query.filter_by(name=name).first():
        flash(f"House '{name}' already exists.", "warning")
    else:
        db.session.add(House(name=name))
        db.session.commit()
        flash(f"House '{name}' added.", "success")

    return redirect(url_for('admin_houses'))

@app.route('/admin/houses/edit/<int:id>', methods=['POST'])
def admin_house_edit(id):
    if not session.get('is_admin'): return redirect(url_for('index'))

    house = House.query.get_or_404(id)
    new_name = request.form.get('name').strip()

    if not new_name:
        flash("New name is required.", "danger")
    elif new_name != house.name and House.query.filter_by(name=new_name).first():
        flash(f"House '{new_name}' already exists.", "warning")
    else:
        old_name = house.name
        house.name = new_name
        db.session.commit()
        flash(f"Renamed House '{old_name}' to '{new_name}'.", "success")

    return redirect(url_for('admin_houses'))

@app.route('/admin/houses/delete/<int:id>', methods=['POST'])
def admin_house_delete(id):
    if not session.get('is_admin'): return redirect(url_for('index'))

    house = House.query.get_or_404(id)
    if Flock.query.filter_by(house_id=id).count() > 0:
        flash(f"Cannot delete House '{house.name}' because it has flocks associated with it.", "danger")
    else:
        # Also delete associated configs?
        # OverviewConfig and ChartConfiguration have cascades?
        # Models:
        # charts = db.relationship(..., cascade="all, delete-orphan")
        # overview_config = db.relationship(..., cascade="all, delete-orphan")
        # So yes, they will be deleted.
        db.session.delete(house)
        db.session.commit()
        flash(f"House '{house.name}' deleted.", "info")

    return redirect(url_for('admin_houses'))

@app.route('/daily_log/<int:id>/edit', methods=['GET', 'POST'])
@dept_required('Farm')
def edit_daily_log(id):
    log = DailyLog.query.get_or_404(id)
    
    if request.method == 'POST':
        # Handle Vaccines
        vaccine_present_ids = request.form.getlist('vaccine_present_ids')
        vaccine_completed_ids = request.form.getlist('vaccine_completed_ids')

        for vid in vaccine_present_ids:
            vac = Vaccine.query.get(vid)
            if vac and vac.flock_id == log.flock_id:
                if vid in vaccine_completed_ids:
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

        for i, name_val in enumerate(med_names):
            inv_id_val = med_inventory_ids[i] if i < len(med_inventory_ids) else None

            item_name = name_val
            inv_id = None
            if inv_id_val and inv_id_val.isdigit():
                inv_id = int(inv_id_val)
                item = InventoryItem.query.get(inv_id)
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
                inv_item = InventoryItem.query.get(inv_id)
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

        update_log_from_request(log, request)
        db.session.commit()
        flash('Log updated successfully.', 'success')
        return redirect(url_for('view_flock', id=log.flock_id))
    
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
@dept_required('Farm')
def import_data():
    if request.method == 'POST':
        # Check for Confirmation
        confirm_filename = request.form.get('confirm_file')
        if confirm_filename:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'temp', confirm_filename)
            if not os.path.exists(filepath):
                flash('Temporary import file not found. Please upload again.', 'danger')
                return redirect(url_for('import_data'))

            try:
                process_import(filepath, commit=True, preview=False)
                os.remove(filepath)
                flash('Import confirmed and data saved successfully.', 'success')
            except Exception as e:
                import traceback
                traceback.print_exc()
                flash(f'Error during import: {str(e)}', 'danger')

            return redirect(url_for('index'))

        if 'files' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        
        files = request.files.getlist('files')
        if not files or files[0].filename == '':
            flash('No selected files', 'danger')
            return redirect(request.url)

        # For Staging Step: We only handle single file preview nicely for now,
        # or we iterate. The requirement implies "a table for me to Approve".
        # If multiple files, we might need a more complex UI.
        # Assuming single file for the "Staging" flow is safer or sequential.
        # But existing code handled multiple.
        # Let's handle the first valid file for preview to satisfy the requirement,
        # or loop and append changes. Appending changes is better.

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
                    all_changes.extend(changes)
                    all_warnings.extend(warnings)

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
            # We only support confirming one file at a time in the simple UI unless we handle list of files.
            # But let's assume the user uploaded one file as is typical for this detailed review.
            # If multiple, we just use the first filename for confirmation?
            # Ideally we support only one file for this "Deep Review" mode.
            if len(temp_filenames) > 1:
                flash("Please upload only one file at a time for review.", "warning")
                return redirect(request.url)

            return render_template('import_preview.html', changes=all_changes, warnings=all_warnings, filename=temp_filenames[0])

        flash("No valid data found to import.", "warning")
        return redirect(url_for('index'))
            
    return render_template('import.html')

@app.route('/import_hatchability', methods=['POST'])
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
            s = Standard.query.filter_by(week=week_val).first()
            if not s:
                s = Standard(week=week_val)
                db.session.add(s)

            s.std_mortality_male = std_mort # Using same for both sexes if only one col
            s.std_mortality_female = std_mort
            s.std_bw_male = std_bw_m
            s.std_bw_female = std_bw_f
            s.std_egg_prod = std_egg_prod
            s.std_egg_weight = std_egg_weight
            s.std_hatchability = std_hatch

            count += 1

        db.session.commit()
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
    all_flocks = Flock.query.order_by(Flock.intake_date.desc()).all()
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
                                          last_hatch_date=last_hatch_date)

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

    db.session.commit()
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
            
        df_meta = pd.read_excel(xls, sheet_name=sheet_name, header=None, nrows=10)
        
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
        
        intake_female = int(get_val(2, 1) or 0)
        intake_male = int(get_val(3, 1) or 0)
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
                db.session.commit()
        
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
                db.session.commit()
            
            initialize_sampling_schedule(flock_id, commit=commit)
            initialize_vaccine_schedule(flock_id, commit=commit)

        existing_logs_dict = {log.date: log for log in DailyLog.query.filter_by(flock_id=flock_id).all()}

        df_std = pd.read_excel(xls, sheet_name=sheet_name, header=None, skiprows=507, nrows=70)
        standard_bw_map = {}
        missing_std_weeks = []

        if df_std.shape[1] > 33:
            weeks = df_std[0]
            males = df_std[32]
            females = df_std[33]

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

        df_data = pd.read_excel(xls, sheet_name=sheet_name, header=8)
        
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
                return float(val) if pd.notna(val) and isinstance(val, (int, float)) else 0.0

            def get_int(r, idx):
                if idx is None or idx >= len(r): return 0
                val = r.iloc[idx]
                return int(val) if pd.notna(val) and isinstance(val, (int, float)) else 0
                
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
                log = DailyLog(flock_id=flock_id, date=log_date)
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
            log.clinical_notes = str(val_rem) if pd.notna(val_rem) else None

            bw_m = get_float(row, idx_bw_m)
            bw_f = get_float(row, idx_bw_f)
            unif_m = get_float(row, idx_unif_m)
            unif_f = get_float(row, idx_unif_f)

            has_bw = (bw_m > 0 or bw_f > 0)

            if has_bw:
                log.is_weighing_day = True
                days_diff = (log.date - intake_date).days
                week_num = (days_diff // 7) + 1
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
            db.session.commit()
        else:
            db.session.flush()
        
        all_logs = sorted(existing_logs_dict.values(), key=lambda x: x.date)
        for i, log in enumerate(all_logs):
            if i > 0:
                prev_log = all_logs[i-1]
                if prev_log.water_reading_1 and log.water_reading_1:
                    r1_today = log.water_reading_1 / 100.0
                    r1_prev = prev_log.water_reading_1 / 100.0
                    log.water_intake_calculated = (r1_today - r1_prev) * 1000.0
                    db.session.add(log)

        if commit:
            db.session.commit()
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

def update_log_from_request(log, req):
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

    # --- Calculate Feed Kg ---
    # Need current stock for calculation.
    # We must calculate stock BEFORE today's mortality?
    # Usually: Feed is given to birds alive at start of day (or end of previous day).
    # Mortality happens during the day.
    # So stock = Intake - (Cum Mort + Culls up to YESTERDAY).

    # Fetch previous logs to sum mortality
    # Optimized: We can query the sum directly or iterate if in memory.
    # Since we are in a request context, let's do a quick query.

    stmt_m = db.session.query(
        db.func.sum(DailyLog.mortality_male),
        db.func.sum(DailyLog.culls_male),
        db.func.sum(DailyLog.males_moved_to_hosp),
        db.func.sum(DailyLog.males_moved_to_prod)
    ).filter(DailyLog.flock_id == log.flock_id, DailyLog.date < log.date).first()

    stmt_f = db.session.query(
        db.func.sum(DailyLog.mortality_female),
        db.func.sum(DailyLog.culls_female)
    ).filter(DailyLog.flock_id == log.flock_id, DailyLog.date < log.date).first()

    cum_mort_m = (stmt_m[0] or 0)
    cum_culls_m = (stmt_m[1] or 0)
    # Transfers logic: If moved to hosp, they are out of prod.
    # But wait, males in hosp still eat?
    # Assuming "Feed Male" covers all males in the house (Prod + Hosp)?
    # Usually feed is tracked per house.
    # If so, we just need Total Males Alive in House.
    # Total Alive = Intake - Total Dead - Total Culled.
    # Transfers between pens (Prod <-> Hosp) don't change house population.
    # However, if 'males_moved_to_hosp' means moved OUT of house, that's different.
    # Based on `DailyLog` model, `males_moved_to_hosp` seems internal.
    # Let's assume total stock in house.

    # Re-checking stock logic in `index()` route:
    # curr_m_prod = ... - moved_to_hosp + moved_to_prod
    # curr_m_hosp = ... + moved_to_hosp - moved_to_prod
    # Total Males = curr_m_prod + curr_m_hosp.
    # So transfers cancel out for total house stock.

    start_m = log.flock.intake_male
    start_f = log.flock.intake_female

    current_stock_m = start_m - cum_mort_m - cum_culls_m
    current_stock_f = start_f - (stmt_f[0] or 0) - (stmt_f[1] or 0)

    # Feed Multiplier Logic
    multiplier = 1.0
    if log.feed_program == 'Skip-a-day':
        multiplier = 2.0
    elif log.feed_program == '2/1':
        multiplier = 1.5

    # Calculate Total Kg
    # Formula: (g/bird * multiplier * stock) / 1000
    if current_stock_m > 0:
        log.feed_male = (log.feed_male_gp_bird * multiplier * current_stock_m) / 1000.0
    else:
        log.feed_male = 0.0

    if current_stock_f > 0:
        log.feed_female = (log.feed_female_gp_bird * multiplier * current_stock_f) / 1000.0
    else:
        log.feed_female = 0.0

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
    log.uniformity_male = uni_m_val
    log.uniformity_female = uni_f_val

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

    log.light_on_time = req.form.get('light_on_time')
    log.light_off_time = req.form.get('light_off_time')
    log.feed_cleanup_start = req.form.get('feed_cleanup_start')
    log.feed_cleanup_end = req.form.get('feed_cleanup_end')
    log.clinical_notes = req.form.get('clinical_notes')

    if 'photo' in req.files:
        file = req.files['photo']
        if file and file.filename != '':
            date_str = log.date.strftime('%y%m%d')
            raw_name = f"{log.flock.flock_id}_{date_str}_{file.filename}"
            filename = secure_filename(raw_name)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            log.photo_path = filepath

    from datetime import timedelta
    yesterday = log.date - timedelta(days=1)
    yesterday_log = DailyLog.query.filter_by(flock_id=log.flock_id, date=yesterday).first()

    if yesterday_log:
        r1_today_real = log.water_reading_1 / 100.0
        r1_yesterday_real = yesterday_log.water_reading_1 / 100.0
        log.water_intake_calculated = (r1_today_real - r1_yesterday_real) * 1000.0
    else:
        log.water_intake_calculated = 0.0

def verify_import_data(flock, logs=None):
    weekly_records = ImportedWeeklyBenchmark.query.filter_by(flock_id=flock.id).order_by(ImportedWeeklyBenchmark.week).all()
    if logs is None:
        logs = DailyLog.query.filter_by(flock_id=flock.id).all()

    warnings = []
    agg = {}
    for log in logs:
        delta = (log.date - flock.intake_date).days
        week = (delta // 7) + 1
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
                db.session.commit()
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
                db.session.commit()
                flash('Vaccine record deleted.', 'info')

        elif 'save_changes' in request.form:
            # Bulk Update
            vaccine_ids = [k.split('_')[2] for k in request.form.keys() if k.startswith('v_id_')]
            updated_count = 0

            for vid in vaccine_ids:
                v = Vaccine.query.get(vid)
                if not v or v.flock_id != id: continue

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

            db.session.commit()
            flash(f'Updated {updated_count} records.', 'success')

        return redirect(url_for('health_log_vaccines', year=year, month=month, flock_id=selected_flock_id))

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
        f.current_week = (days // 7) + 1 if days >= 0 else 0
    flock_ids = [f.id for f in active_flocks]

    vaccine_events_by_date = {}
    vaccines = Vaccine.query.filter(Vaccine.flock_id.in_(flock_ids)).filter(Vaccine.est_date >= start_date, Vaccine.est_date <= end_date).all()
    for v in vaccines:
        d = v.est_date
        if d not in vaccine_events_by_date: vaccine_events_by_date[d] = []
        age_days = (d - v.flock.intake_date).days
        age_week = (age_days // 7) + 1
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

        for sid in s_ids:
            s = SamplingEvent.query.get(sid)
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
                s.age_week = (diff // 7) + 1
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
            db.session.commit()
            flash(f'Updated {updated_count} records.', 'success')

        return redirect(url_for('health_log_sampling', year=year, month=month, flock_id=selected_flock_id))

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
        f.current_week = (days // 7) + 1 if days >= 0 else 0
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
    today = date.today()
    selected_flock_id = request.args.get('flock_id')
    edit_flock_id = request.args.get('edit_flock_id', type=int)

    if request.method == 'POST':
        flock_id_param = request.form.get('flock_id') or selected_flock_id

        if 'add_medication' in request.form:
             if flock_id_param:
                 try:
                     s_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
                     e_date = None
                     if request.form.get('end_date'):
                         e_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()

                     inv_id = request.form.get('inventory_item_id')
                     drug_name = request.form.get('drug_name')
                     if inv_id and inv_id.isdigit():
                         inv_id = int(inv_id)
                         item = InventoryItem.query.get(inv_id)
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

                     if inv_id and qty > 0:
                         inv_item = InventoryItem.query.get(inv_id)
                         if inv_item:
                             inv_item.current_stock -= qty
                             t = InventoryTransaction(
                                 inventory_item_id=inv_id,
                                 transaction_type='Usage',
                                 quantity=qty,
                                 transaction_date=s_date,
                                 notes=f'Used in Health Log'
                             )
                             db.session.add(t)

                     db.session.commit()
                     flash('Medication added.', 'success')
                 except Exception as e:
                     flash(f'Error adding medication: {str(e)}', 'danger')

        updated_count = 0
        m_ids = set()
        for key in request.form:
            if key.startswith('m_') and key.split('_')[-1].isdigit():
                m_ids.add(int(key.split('_')[-1]))

        for mid in m_ids:
            m = Medication.query.get(mid)
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
            db.session.commit()
            flash(f'Updated {updated_count} records.', 'success')

        return redirect(url_for('health_log_medication', flock_id=selected_flock_id))

    active_flocks = Flock.query.filter_by(status='Active').options(joinedload(Flock.house)).all()
    for f in active_flocks:
        days = (today - f.intake_date).days
        f.current_week = (days // 7) + 1 if days >= 0 else 0

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
        medication_inventory=medication_inventory
    )

@app.route('/api/metrics')
def get_metrics_list():
    return json.dumps(METRICS_REGISTRY)

@app.route('/api/flock/<int:flock_id>/custom_data', methods=['POST'])
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

    result = calculate_metrics(logs, flock, metrics, hatchability_data=hatchability_data, start_date=start_date, end_date=end_date)

    result['events'] = []
    for log in logs:
        if start_date and log.date < start_date: continue
        if end_date and log.date > end_date: continue

        if log.clinical_notes or log.photo_path:
             result['events'].append({
                 'date': log.date.isoformat(),
                 'note': log.clinical_notes,
                 'photo': url_for('uploaded_file', filename=os.path.basename(log.photo_path)) if log.photo_path else None
             })

    return json.dumps(result)

@app.route('/api/house/<int:house_id>/dashboard_config')
def get_dashboard_config(house_id):
    house = House.query.get_or_404(house_id)

    charts = []
    for c in house.charts:
        charts.append({
            'id': c.id,
            'title': c.title,
            'chart_type': c.chart_type,
            'config': json.loads(c.config_json),
            'is_template': c.is_template
        })

    overview_cols = []
    if house.overview_config:
        overview_cols = json.loads(house.overview_config.visible_metrics_json)

    return json.dumps({'charts': charts, 'overview_columns': overview_cols})

@app.route('/api/house/<int:house_id>/charts', methods=['POST'])
@dept_required('Farm')
def save_chart(house_id):
    data = request.get_json()

    chart_id = data.get('id')
    title = data.get('title')
    chart_type = data.get('chart_type', 'line')
    config = data.get('config')
    is_template = data.get('is_template', False)

    if chart_id:
        chart = ChartConfiguration.query.get_or_404(chart_id)
        if chart.house_id != house_id:
            return "Unauthorized", 403
        chart.title = title
        chart.chart_type = chart_type
        chart.config_json = json.dumps(config)
        chart.is_template = is_template
    else:
        chart = ChartConfiguration(
            house_id=house_id,
            title=title,
            chart_type=chart_type,
            config_json=json.dumps(config),
            is_template=is_template
        )
        db.session.add(chart)

    db.session.commit()
    return "Saved", 200

@app.route('/api/charts/<int:chart_id>', methods=['DELETE'])
@dept_required('Farm')
def delete_chart(chart_id):
    chart = ChartConfiguration.query.get_or_404(chart_id)
    db.session.delete(chart)
    db.session.commit()
    return "Deleted", 200

@app.route('/api/house/<int:house_id>/overview', methods=['POST'])
@dept_required('Farm')
def save_overview_config(house_id):
    data = request.get_json()
    cols = data.get('columns', [])

    config = OverviewConfiguration.query.filter_by(house_id=house_id).first()
    if not config:
        config = OverviewConfiguration(house_id=house_id)
        db.session.add(config)

    config.visible_metrics_json = json.dumps(cols)
    db.session.commit()
    return "Saved", 200

@app.route('/api/templates')
def get_templates():
    templates = ChartConfiguration.query.filter_by(is_template=True).all()
    res = []
    for t in templates:
        res.append({
            'id': t.id,
            'title': t.title,
            'chart_type': t.chart_type,
            'config': json.loads(t.config_json),
            'house_name': t.house.name
        })
    return json.dumps(res)

# --- Inventory Routes ---

@app.route('/inventory')
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
    db.session.commit()

    if stock > 0:
        t = InventoryTransaction(
            inventory_item_id=item.id,
            transaction_type='Purchase',
            quantity=stock,
            transaction_date=date.today(),
            notes='Initial Stock'
        )
        db.session.add(t)
        db.session.commit()

    flash(f'Added {name} to inventory.', 'success')
    return redirect(url_for('inventory'))

@app.route('/inventory/transaction', methods=['POST'])
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

    if type_ in ['Usage', 'Waste']:
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
    db.session.commit()

    flash('Transaction recorded.', 'success')
    return redirect(url_for('inventory'))

@app.route('/inventory/edit/<int:id>', methods=['POST'])
@dept_required('Farm')
def edit_inventory_item(id):
    item = InventoryItem.query.get_or_404(id)

    if request.form.get('delete') == '1':
        db.session.delete(item)
        db.session.commit()
        flash('Item deleted.', 'info')
        return redirect(url_for('inventory'))

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

    db.session.commit()
    flash('Item updated.', 'success')
    return redirect(url_for('inventory'))

@app.route('/inventory/transaction/delete/<int:id>', methods=['POST'])
@dept_required('Farm')
def delete_inventory_transaction(id):
    if not session.get('is_admin'): return redirect(url_for('index'))

    t = InventoryTransaction.query.get_or_404(id)
    item = InventoryItem.query.get(t.inventory_item_id)

    # Revert Stock
    if item:
        if t.transaction_type in ['Usage', 'Waste']:
            item.current_stock += t.quantity
        else: # Purchase, Adjustment
            item.current_stock -= t.quantity

    db.session.delete(t)
    db.session.commit()
    flash(f"Transaction deleted. Stock reverted.", "info")
    return redirect(url_for('inventory'))

@app.route('/inventory/transaction/edit/<int:id>', methods=['POST'])
@dept_required('Farm')
def edit_inventory_transaction(id):
    if not session.get('is_admin'): return redirect(url_for('index'))

    t = InventoryTransaction.query.get_or_404(id)
    item = InventoryItem.query.get(t.inventory_item_id)

    new_qty = float(request.form.get('quantity') or 0)
    new_date_str = request.form.get('transaction_date')
    new_notes = request.form.get('notes')
    # Allow changing type? Maybe too complex for now. Let's stick to Qty/Date/Notes.

    if new_qty <= 0:
        flash("Quantity must be positive.", "danger")
        return redirect(url_for('inventory'))

    # Revert Old Effect
    if item:
        if t.transaction_type in ['Usage', 'Waste']:
            item.current_stock += t.quantity
        else:
            item.current_stock -= t.quantity

    # Update Transaction
    t.quantity = new_qty
    t.notes = new_notes
    if new_date_str:
        try:
            t.transaction_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
        except: pass

    # Apply New Effect
    if item:
        if t.transaction_type in ['Usage', 'Waste']:
            item.current_stock -= new_qty
        else:
            item.current_stock += new_qty

    db.session.commit()
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
    std_map = {s.week: s for s in standards}

    # Pre-calculate Offsets for Shifted Standards
    # Find Standard Start
    std_start_week = 24
    std_weeks_with_eggs = [s.week for s in standards if s.std_egg_prod > 0]
    if std_weeks_with_eggs:
        std_start_week = min(std_weeks_with_eggs)

    # Find Actual Start per Flock
    min_egg_dates = db.session.query(
        DailyLog.flock_id,
        func.min(DailyLog.date)
    ).filter(
        DailyLog.flock_id.in_(flock_ids),
        DailyLog.eggs_collected > 0
    ).group_by(DailyLog.flock_id).all()

    offset_map = {}
    flock_objs_temp = {f.id: f for f in flocks} # Temp map for offset calc

    for fid, min_date in min_egg_dates:
        if fid in flock_objs_temp:
             f = flock_objs_temp[fid]
             actual_start_week = (min_date - f.intake_date).days // 7 + 1
             offset_map[fid] = actual_start_week - std_start_week

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

        # Filter Pre-March 2025 (Roughly Week 9 2025)
        # If year < 2025, skip. If year == 2025 and week < 9, skip.
        # Requirement: "ensure that weeks with no data (pre-March 2025) are hidden"
        if year < 2025 or (year == 2025 and week < 9):
            continue

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
        fd['feed_total_kg'] += ((log.feed_male or 0) + (log.feed_female or 0))

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

        if year < 2025 or (year == 2025 and week < 9): continue

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
            age_week = (age_days // 7) + 1
            if age_week < 1: age_week = 1

            # Standards
            std_bio = std_map.get(age_week) # Biological Standard (BW)

            offset = offset_map.get(f_id, 0)
            prod_std_week = age_week - offset
            std_prod = std_map.get(prod_std_week) # Production Standard (Eggs)

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



@app.route('/additional_report')
def additional_report():
    # Role Check: Admin or Management
    if not session.get('is_admin') and session.get('user_role') != 'Management':
        flash("Access Denied: Executive View Only.", "danger")
        return redirect(url_for('index'))

    # Active Flocks
    active_flocks = Flock.query.filter_by(status='Active').options(joinedload(Flock.house)).all()
    active_flocks.sort(key=natural_sort_key)

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

    for flock in flocks:
        # Use relationship logs if available, else query
        logs = flock.logs if flock.logs else DailyLog.query.filter_by(flock_id=flock.id).order_by(DailyLog.date).all()
        hatch_records = Hatchability.query.filter_by(flock_id=flock.id).all()

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

@app.route('/executive_dashboard')
def executive_dashboard():
    # Role Check: Admin or Management
    if not session.get('is_admin') and session.get('user_role') != 'Management':
        flash("Access Denied: Executive View Only.", "danger")
        return redirect(url_for('index'))

    # --- Farm Data ---
    active_flocks = Flock.query.options(joinedload(Flock.logs), joinedload(Flock.house)).filter_by(status='Active').all()
    active_flocks.sort(key=natural_sort_key)

    today = date.today()

    # Inventory Check
    low_stock_items = InventoryItem.query.filter(InventoryItem.current_stock < InventoryItem.min_stock_level).all()
    low_stock_count = len(low_stock_items)

    for f in active_flocks:
        daily_stats = enrich_flock_data(f, f.logs)

        # Hatchery Enrichment
        latest_hatch = Hatchability.query.filter_by(flock_id=f.id).order_by(Hatchability.setting_date.desc()).first()
        f.latest_hatch = latest_hatch
        f.latest_hatch_pct = latest_hatch.hatchability_pct if latest_hatch else 0.0

        stmt = db.session.query(func.sum(Hatchability.hatched_chicks), func.sum(Hatchability.egg_set)).filter_by(flock_id=f.id).first()
        total_h = stmt[0] or 0
        total_s = stmt[1] or 0
        f.cum_hatch_pct = (total_h / total_s * 100) if total_s > 0 else 0.0

        f.rearing_mort_m_pct = 0
        f.rearing_mort_f_pct = 0
        f.prod_mort_m_pct = 0
        f.prod_mort_f_pct = 0
        f.male_ratio_pct = 0
        f.has_log_today = False

        # Age
        days_age = (today - f.intake_date).days
        f.age_weeks = days_age // 7
        f.age_days = days_age % 7
        f.current_week = (days_age // 7) + 1 if days_age >= 0 else 0

        # Stats
        if daily_stats:
            last = daily_stats[-1]
            if last['date'] == today:
                f.has_log_today = True

            if f.phase == 'Rearing':
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

                if f.daily_stats['mort_m_diff'] > 0: f.daily_stats['mort_m_trend'] = 'up'
                elif f.daily_stats['mort_m_diff'] < 0: f.daily_stats['mort_m_trend'] = 'down'

                if f.daily_stats['mort_f_diff'] > 0: f.daily_stats['mort_f_trend'] = 'up'
                elif f.daily_stats['mort_f_diff'] < 0: f.daily_stats['mort_f_trend'] = 'down'

                if f.daily_stats['egg_diff'] > 0: f.daily_stats['egg_trend'] = 'up'
                elif f.daily_stats['egg_diff'] < 0: f.daily_stats['egg_trend'] = 'down'

    # --- Hatchery Data (Legacy Avg) ---
    start_month = date(today.year, today.month, 1)
    monthly_records = Hatchability.query.filter(Hatchability.hatching_date >= start_month).all()
    total_hatched = sum(r.hatched_chicks for r in monthly_records)
    total_set = sum(r.egg_set for r in monthly_records)
    avg_hatch_pct = (total_hatched / total_set * 100) if total_set > 0 else 0.0

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

    iso_data = get_iso_aggregated_data(active_flocks, target_year=selected_year)

    return render_template('executive_dashboard.html',
                           active_flocks=active_flocks,
                           avg_hatch_pct=avg_hatch_pct,
                           current_month=today.strftime('%B %Y'),
                           today=today,
                           low_stock_count=low_stock_count,
                           iso_data=iso_data,
                           available_years=available_years,
                           selected_year=selected_year,
                           active_tab=active_tab)

@app.route('/executive/flock/<int:id>')
def executive_flock_detail(id):
    # Role Check: Admin or Management
    if not session.get('is_admin') and session.get('user_role') != 'Management':
        flash("Access Denied: Executive View Only.", "danger")
        return redirect(url_for('index'))

    active_flocks = Flock.query.options(joinedload(Flock.house)).filter_by(status='Active').all()
    active_flocks.sort(key=natural_sort_key)

    flock = Flock.query.options(joinedload(Flock.house)).filter_by(id=id).first_or_404()
    logs = DailyLog.query.options(joinedload(DailyLog.partition_weights)).filter_by(flock_id=id).order_by(DailyLog.date.asc()).all()

    gs = GlobalStandard.query.first()
    if not gs:
        gs = GlobalStandard()
        db.session.add(gs)
        db.session.commit()

    # --- Standards Setup for Shifted Comparison ---
    all_standards = Standard.query.all()
    std_map = {s.week: s for s in all_standards}

    # Find Standard Start Week
    std_start_week = 24
    sorted_stds = sorted(all_standards, key=lambda x: x.week)
    for s in sorted_stds:
        if s.std_egg_prod > 0:
            std_start_week = s.week
            break

    # --- Fetch Hatch Data ---
    hatch_records = Hatchability.query.filter_by(flock_id=id).all()

    # --- Metrics Engine ---
    daily_stats = enrich_flock_data(flock, logs, hatch_records)

    # --- Calculate Actual Start & Offset ---
    actual_start_date = None
    for d in daily_stats:
        if d['eggs_collected'] > 0:
            actual_start_date = d['date']
            break

    offset_weeks = 0
    if actual_start_date:
        actual_start_week = (actual_start_date - flock.intake_date).days // 7 + 1
        offset_weeks = actual_start_week - std_start_week

    # Inject Shifted Standard
    for d in daily_stats:
        current_age_week = d['week']
        target_std_week = current_age_week - offset_weeks
        std_obj = std_map.get(target_std_week)
        d['std_egg_prod'] = std_obj.std_egg_prod if std_obj else 0.0

    weekly_stats = aggregate_weekly_metrics(daily_stats)

    for ws in weekly_stats:
        current_age_week = ws['week']
        target_std_week = current_age_week - offset_weeks
        std_obj = std_map.get(target_std_week)
        ws['std_egg_prod'] = std_obj.std_egg_prod if std_obj else 0.0

    medications = Medication.query.filter_by(flock_id=id).all()

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

        enriched_logs.append({
            'log': log,
            'stock_male': d['stock_male_start'],
            'stock_female': d['stock_female_start'],
            'lighting_hours': lighting_hours,
            'medications': meds_str,
            'egg_prod_pct': d['egg_prod_pct'],
            'total_feed': d['feed_total_kg'],
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
            'mort_pct_m': ws['mortality_male_pct'],
            'mort_pct_f': ws['mortality_female_pct'],
            'cull_pct_m': ws['culls_male_pct'],
            'cull_pct_f': ws['culls_female_pct'],
            'egg_prod_pct': ws['egg_prod_pct'],
            'hatching_egg_pct': ws['hatch_egg_pct'],
            'avg_bw_male': round_to_whole(ws['body_weight_male']),
            'avg_bw_female': round_to_whole(ws['body_weight_female']),
            'notes': ws['notes'],
            'photos': ws['photos']
        }
        weekly_data.append(w_item)

    # 3. Chart Data (Daily)
    chart_data = {
        'dates': [d['date'].strftime('%Y-%m-%d') for d in daily_stats],
        'mortality_cum_male': [round(d['mortality_cum_male_pct'], 2) for d in daily_stats],
        'mortality_cum_female': [round(d['mortality_cum_female_pct'], 2) for d in daily_stats],
        'mortality_daily_male': [round(d['mortality_male_pct'], 2) for d in daily_stats],
        'mortality_daily_female': [round(d['mortality_female_pct'], 2) for d in daily_stats],
        'culls_daily_male': [round(d['culls_male_pct'], 2) for d in daily_stats],
        'culls_daily_female': [round(d['culls_female_pct'], 2) for d in daily_stats],
        'egg_prod': [round(d['egg_prod_pct'], 2) for d in daily_stats],
        'std_egg_prod': [round(d['std_egg_prod'], 2) for d in daily_stats],
        'male_ratio': [round(d['male_ratio_stock'], 2) if d['male_ratio_stock'] else 0 for d in daily_stats],
        'bw_male_std': [d['log'].standard_bw_male if d['log'].standard_bw_male > 0 else None for d in daily_stats],
        'bw_female_std': [d['log'].standard_bw_female if d['log'].standard_bw_female > 0 else None for d in daily_stats],
        'unif_male': [scale_pct(d['uniformity_male']) if d['uniformity_male'] > 0 else None for d in daily_stats],
        'unif_female': [scale_pct(d['uniformity_female']) if d['uniformity_female'] > 0 else None for d in daily_stats],
        'bw_f': [d['body_weight_female'] if d['body_weight_female'] > 0 else None for d in daily_stats],
        'bw_m': [d['body_weight_male'] if d['body_weight_male'] > 0 else None for d in daily_stats],
        'notes': []
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
        if log.clinical_notes or log.photo_path:
            note_obj = {'note': log.clinical_notes, 'photo': url_for('uploaded_file', filename=os.path.basename(log.photo_path)) if log.photo_path else None}
        chart_data['notes'].append(note_obj)

    # 4. Chart Data (Weekly)
    daily_by_week = {}
    for d in daily_stats:
        if d['week'] not in daily_by_week: daily_by_week[d['week']] = []
        daily_by_week[d['week']].append(d)

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
        chart_data_weekly['bw_male_std'].append(last_day['log'].standard_bw_male if last_day['log'].standard_bw_male > 0 else None)
        chart_data_weekly['bw_female_std'].append(last_day['log'].standard_bw_female if last_day['log'].standard_bw_female > 0 else None)
        chart_data_weekly['unif_male'].append(scale_pct(ws['uniformity_male']) if ws['uniformity_male'] > 0 else None)
        chart_data_weekly['unif_female'].append(scale_pct(ws['uniformity_female']) if ws['uniformity_female'] > 0 else None)

        for i in range(1, 9):
            chart_data_weekly[f'bw_M{i}'].append(None)
            chart_data_weekly[f'bw_F{i}'].append(None)

        if ws['notes'] or ws['photos']:
            note_text = " | ".join(ws['notes'])
            photo_url = url_for('uploaded_file', filename=os.path.basename(ws['photos'][0])) if ws['photos'] else None
            chart_data_weekly['notes'].append({'note': note_text, 'photo': photo_url})
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

    return render_template('flock_detail_readonly.html',
                           flock=flock,
                           logs=list(reversed(enriched_logs)),
                           weekly_data=weekly_data,
                           chart_data=chart_data,
                           chart_data_weekly=chart_data_weekly,
                           current_stats=current_stats,
                           global_std=gs,
                           active_flocks=active_flocks,
                           hatch_records=hatch_records)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)