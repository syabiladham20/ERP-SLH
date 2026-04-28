from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from sqlalchemy.orm import declared_attr
from app.extensions import login_manager
from app.database import db


class VersionedMixin(object):
    version = db.Column(db.Integer, nullable=False, default=1, server_default='1')

    @declared_attr
    def __mapper_args__(cls):
        return {
            "version_id_col": cls.version
        }


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



@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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



class InventoryItem(VersionedMixin, db.Model):
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

class InventoryTransaction(VersionedMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey('inventory_item.id'), nullable=False, index=True)
    transaction_type = db.Column(db.String(20), nullable=False) # 'Purchase', 'Usage', 'Adjustment', 'Waste'
    quantity = db.Column(db.Float, nullable=False)
    transaction_date = db.Column(db.Date, nullable=False, default=date.today, index=True)
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

class DailyLog(VersionedMixin, db.Model):
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
    feed_code_male_id = db.Column(db.Integer, db.ForeignKey('feed_code.id'), nullable=True, index=True)
    feed_code_female_id = db.Column(db.Integer, db.ForeignKey('feed_code.id'), nullable=True, index=True)

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

class ChartNote(VersionedMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flock_id = db.Column(db.Integer, db.ForeignKey('flock.id'), nullable=False, index=True)
    chart_identifier = db.Column(db.String(50), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    pos_x = db.Column(db.Float, nullable=False)
    pos_y = db.Column(db.Float, nullable=False)
    width = db.Column(db.Float, nullable=False)
    height = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class FloatingNote(VersionedMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flock_id = db.Column(db.Integer, db.ForeignKey('flock.id'), nullable=False, index=True)
    chart_id = db.Column(db.String(50), nullable=False) # e.g. 'generalChart', 'waterChart'
    x_value = db.Column(db.String(50), nullable=False, index=True) # X-axis date string or value
    y_value = db.Column(db.Float, nullable=False) # Y-axis value
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class ClinicalNote(VersionedMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    log_id = db.Column(db.Integer, db.ForeignKey('daily_log.id'), nullable=False, index=True)
    caption = db.Column(db.String(255))
    photos = db.relationship('DailyLogPhoto', backref='note', lazy=True)

class DailyLogPhoto(VersionedMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    log_id = db.Column(db.Integer, db.ForeignKey('daily_log.id'), nullable=False, index=True)
    note_id = db.Column(db.Integer, db.ForeignKey('clinical_note.id'), nullable=True, index=True)
    file_path = db.Column(db.String(200), nullable=False)
    original_filename = db.Column(db.String(200), nullable=True)

class PartitionWeight(VersionedMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    log_id = db.Column(db.Integer, db.ForeignKey('daily_log.id'), nullable=False, index=True)
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

class UIElement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    label = db.Column(db.String(100), nullable=False)
    section = db.Column(db.String(50), nullable=False) # 'navbar_main', 'navbar_health', 'flock_card', 'flock_detail'
    is_visible = db.Column(db.Boolean, default=True)
    order_index = db.Column(db.Integer, default=0)

class SamplingEvent(VersionedMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flock_id = db.Column(db.Integer, db.ForeignKey('flock.id'), nullable=False, index=True)
    flock = db.relationship('Flock', backref=db.backref('sampling_events', cascade="all, delete-orphan"))
    age_week = db.Column(db.Integer, nullable=False, index=True)
    test_type = db.Column(db.String(50), nullable=False) # 'Serology', 'Salmonella', 'Serology & Salmonella'
    status = db.Column(db.String(20), default='Pending', index=True) # 'Pending', 'Completed'
    result_file = db.Column(db.String(200), nullable=True) # Path to PDF
    upload_date = db.Column(db.Date, nullable=True)
    actual_date = db.Column(db.Date, nullable=True)
    remarks = db.Column(db.String(255), nullable=True)
    scheduled_date = db.Column(db.Date, nullable=True)

class Medication(VersionedMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flock_id = db.Column(db.Integer, db.ForeignKey('flock.id'), nullable=False, index=True)
    drug_name = db.Column(db.String(100), nullable=False)
    dosage = db.Column(db.String(50), nullable=False)
    amount_used = db.Column(db.String(100), nullable=True)
    amount_used_qty = db.Column(db.Float, nullable=True)
    withdrawal_period_days = db.Column(db.Integer, default=0)
    start_date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    end_date = db.Column(db.Date, nullable=True, index=True)
    remarks = db.Column(db.String(255), nullable=True)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey('inventory_item.id'), nullable=True, index=True)

    flock = db.relationship('Flock', backref=db.backref('medications', lazy=True, cascade="all, delete-orphan"))

class Vaccine(VersionedMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flock_id = db.Column(db.Integer, db.ForeignKey('flock.id'), nullable=False, index=True)
    # Age can be defined by Day (for first few weeks) or Week
    age_code = db.Column(db.String(10), nullable=False) # 'D1', 'W6', etc.
    vaccine_name = db.Column(db.String(200), nullable=False)
    route = db.Column(db.String(50), nullable=True)

    # Dates
    est_date = db.Column(db.Date, nullable=True, index=True)
    actual_date = db.Column(db.Date, nullable=True, index=True)
    remarks = db.Column(db.String(255), nullable=True)
    doses_per_unit = db.Column(db.Integer, default=1000)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey('inventory_item.id'), nullable=True, index=True)

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

class FlockGrading(VersionedMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    house_id = db.Column(db.Integer, db.ForeignKey('house.id'), nullable=False, index=True)
    age_week = db.Column(db.Integer, nullable=False, index=True)
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

class Hatchability(VersionedMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flock_id = db.Column(db.Integer, db.ForeignKey('flock.id'), nullable=False, index=True)
    setting_date = db.Column(db.Date, nullable=False, index=True)
    candling_date = db.Column(db.Date, nullable=False, index=True)
    hatching_date = db.Column(db.Date, nullable=False, index=True)

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
class BroilerFlock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    farm_name = db.Column(db.String(100), nullable=True)
    house_name = db.Column(db.String(100), nullable=True)
    source = db.Column(db.String(100), nullable=True)
    breed = db.Column(db.String(50), nullable=True)
    intake_birds = db.Column(db.Integer, default=0, nullable=False)
    intake_date = db.Column(db.Date, nullable=False, default=date.today)
    arrival_weight_g = db.Column(db.Float, default=0.0)
    is_active = db.Column(db.Boolean, default=True)

    logs = db.relationship('BroilerDailyLog', backref='flock', lazy=True, cascade="all, delete-orphan")

class BroilerDailyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flock_id = db.Column(db.Integer, db.ForeignKey('broiler_flock.id'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    day_number = db.Column(db.Integer, nullable=False)
    death_count = db.Column(db.Integer, default=0)
    feed_receive = db.Column(db.String(100), nullable=True)
    feed_type = db.Column(db.String(100), nullable=True)
    feed_daily_use_kg = db.Column(db.Float, default=0.0)
    body_weight_g = db.Column(db.Float, default=0.0)
    standard_fcr = db.Column(db.Float, default=0.0)
    medication_vaccine = db.Column(db.String(200), nullable=True)
    remarks = db.Column(db.Text, nullable=True)

class AnonymousUser:
    is_authenticated = False
    username = ''
    role = ''
