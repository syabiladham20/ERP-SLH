from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from datetime import datetime, date
import os
from flask import send_from_directory
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'farm.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev_key')
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)

@app.template_filter('basename')
def basename_filter(s):
    if not s:
        return None
    return os.path.basename(str(s).replace('\\', '/'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

db = SQLAlchemy(app)

class FeedCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)

class House(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    flocks = db.relationship('Flock', backref='house', lazy=True)

class Flock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    house_id = db.Column(db.Integer, db.ForeignKey('house.id'), nullable=False)
    batch_id = db.Column(db.String(100), unique=True, nullable=False)
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
    end_date = db.Column(db.Date, nullable=True)
    
    logs = db.relationship('DailyLog', backref='flock', lazy=True, cascade="all, delete-orphan")
    weekly_data = db.relationship('WeeklyData', backref='flock', lazy=True, cascade="all, delete-orphan")
    weekly_benchmarks = db.relationship('ImportedWeeklyBenchmark', backref='flock', lazy=True, cascade="all, delete-orphan")

class DailyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flock_id = db.Column(db.Integer, db.ForeignKey('flock.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    
    # Metrics
    mortality_male = db.Column(db.Integer, default=0) # Production Mortality
    mortality_female = db.Column(db.Integer, default=0)
    
    mortality_male_hosp = db.Column(db.Integer, default=0) # Hospital Mortality
    culls_male_hosp = db.Column(db.Integer, default=0) # Hospital Culls

    culls_male = db.Column(db.Integer, default=0) # Production Culls
    culls_female = db.Column(db.Integer, default=0)
    
    # Transfers
    males_moved_to_prod = db.Column(db.Integer, default=0)
    males_moved_to_hosp = db.Column(db.Integer, default=0)

    feed_program = db.Column(db.String(50)) # 'Full Feed', 'Skip-a-day'
    # Feed (Grams per Bird)
    feed_male_gp_bird = db.Column(db.Float, default=0.0)
    feed_female_gp_bird = db.Column(db.Float, default=0.0)
    
    eggs_collected = db.Column(db.Integer, default=0)
    
    cull_eggs_jumbo = db.Column(db.Integer, default=0)
    cull_eggs_small = db.Column(db.Integer, default=0)
    cull_eggs_abnormal = db.Column(db.Integer, default=0)
    cull_eggs_crack = db.Column(db.Integer, default=0)
    
    egg_weight = db.Column(db.Float, default=0.0)
    
    # Body Weight (Split by Sex)
    body_weight_male = db.Column(db.Float, default=0.0)
    body_weight_female = db.Column(db.Float, default=0.0)
    uniformity_male = db.Column(db.Float, default=0.0)
    uniformity_female = db.Column(db.Float, default=0.0)

    # Partitions & Weighing Day
    is_weighing_day = db.Column(db.Boolean, default=False)

    bw_male_p1 = db.Column(db.Float, default=0.0)
    bw_male_p2 = db.Column(db.Float, default=0.0)
    unif_male_p1 = db.Column(db.Float, default=0.0)
    unif_male_p2 = db.Column(db.Float, default=0.0)

    bw_female_p1 = db.Column(db.Float, default=0.0)
    bw_female_p2 = db.Column(db.Float, default=0.0)
    bw_female_p3 = db.Column(db.Float, default=0.0)
    bw_female_p4 = db.Column(db.Float, default=0.0)
    unif_female_p1 = db.Column(db.Float, default=0.0)
    unif_female_p2 = db.Column(db.Float, default=0.0)
    unif_female_p3 = db.Column(db.Float, default=0.0)
    unif_female_p4 = db.Column(db.Float, default=0.0)

    standard_bw_male = db.Column(db.Float, default=0.0)
    standard_bw_female = db.Column(db.Float, default=0.0)
    
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

    feed_code_id = db.Column(db.Integer, db.ForeignKey('feed_code.id'), nullable=True)
    feed_code = db.relationship('FeedCode', backref='daily_logs')

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
    body_weight = db.Column(db.Float, default=0.0)
    uniformity = db.Column(db.Float, default=0.0)

class Standard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    week = db.Column(db.Integer, unique=True, nullable=False)
    std_mortality_male = db.Column(db.Float, default=0.0)
    std_mortality_female = db.Column(db.Float, default=0.0)
    std_bw_male = db.Column(db.Float, default=0.0)
    std_bw_female = db.Column(db.Float, default=0.0)
    std_egg_prod = db.Column(db.Float, default=0.0)
    std_feed_male = db.Column(db.Float, default=0.0)
    std_feed_female = db.Column(db.Float, default=0.0)

class WeeklyData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flock_id = db.Column(db.Integer, db.ForeignKey('flock.id'), nullable=False)
    week = db.Column(db.Integer, nullable=False)

    mortality_male = db.Column(db.Integer, default=0)
    mortality_female = db.Column(db.Integer, default=0)
    culls_male = db.Column(db.Integer, default=0)
    culls_female = db.Column(db.Integer, default=0)

    eggs_collected = db.Column(db.Integer, default=0)

    bw_male = db.Column(db.Float, default=0.0)
    bw_female = db.Column(db.Float, default=0.0)

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
    remarks = db.Column(db.String(255), nullable=True)

    @property
    def scheduled_date(self):
        from datetime import timedelta
        # Week 1 starts on Day 1 (Intake Date + 1).
        # Week N starts on Intake + 1 + (N-1)*7 days.
        days_offset = ((self.age_week - 1) * 7) + 1
        return self.flock.intake_date + timedelta(days=days_offset)

class Medication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flock_id = db.Column(db.Integer, db.ForeignKey('flock.id'), nullable=False)
    drug_name = db.Column(db.String(100), nullable=False)
    dosage = db.Column(db.String(50), nullable=False)
    withdrawal_period_days = db.Column(db.Integer, default=0)
    start_date = db.Column(db.Date, nullable=False, default=date.today)
    end_date = db.Column(db.Date, nullable=True)
    remarks = db.Column(db.String(255), nullable=True)

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

    flock = db.relationship('Flock', backref=db.backref('vaccines', lazy=True, cascade="all, delete-orphan"))

    @property
    def dose_count(self):
        # "Round up the doses by overestimate the bird population, if 7500 birds, count as 8000 birds."
        # Assuming 1000 doses per bottle as per prompt.
        if not self.flock: return 0

        # Determine bird count (Intake or Current?)
        # "From D1 is week 0... if 7500 birds, count as 8000"
        # Usually based on Intake or Current Stock. Let's use Intake for simplicity/safety or Current?
        # Safe to use Intake or Current. Prompt says "bird population".
        # Let's use a rough current stock estimation or just Intake for D1.
        # But for W56, many birds might have died.
        # Let's use 'current stock' estimation based on phase?
        # Actually, simpler: Use Intake for now, or refine later.
        # Prompt: "overestimate the bird population".
        count = self.flock.intake_female + self.flock.intake_male
        import math
        # Round up to nearest 1000? "if 7500 ... count as 8000"
        # 7500 / 1000 = 7.5 -> ceil -> 8 * 1000 = 8000
        doses_needed = math.ceil(count / 1000.0) * 1000
        return doses_needed

class ImportedWeeklyBenchmark(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flock_id = db.Column(db.Integer, db.ForeignKey('flock.id'), nullable=False)
    week = db.Column(db.Integer, nullable=False)

    mortality_male = db.Column(db.Integer, default=0)
    mortality_female = db.Column(db.Integer, default=0)
    eggs_collected = db.Column(db.Integer, default=0)
    bw_male = db.Column(db.Float, default=0.0)
    bw_female = db.Column(db.Float, default=0.0)

def initialize_sampling_schedule(flock_id):
    # Updated Schedule based on user input
    # Week 1 (Day 1): SEROLOGY AND SALMONELLA
    # Week 4: SALMONELLA
    # Week 8: SEROLOGY
    # Week 16: SALMONELLA
    # Week 18: SEROLOGY
    # Week 24: SEROLOGY
    # Week 28: SALMONELLA
    # Week 30: SEROLOGY
    # Week 38: SEROLOGY
    # Week 40: SALMONELLA
    # Week 50: SEROLOGY
    # Week 52: SALMONELLA
    # Week 58: SEROLOGY
    # Week 64: SALMONELLA
    # Week 70: SEROLOGY
    # Week 76: SALMONELLA
    # Week 90: SALMONELLA

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

    for week, test in schedule.items():
        event = SamplingEvent(
            flock_id=flock_id,
            age_week=week,
            test_type=test,
            status='Pending'
        )
        db.session.add(event)
    db.session.commit()

def initialize_vaccine_schedule(flock_id):
    flock = Flock.query.get(flock_id)
    if not flock: return

    # Schedule from prompt
    # Structure: (AgeCode, VaccineName, Route, DaysOffset)
    # D1 = 0 days from Intake (assuming Intake is Day 1 or Day 0? usually Intake is Day 0/1)
    # Prompt: "From D1 is week 0".
    # We will assume Intake Date = D1 (Day 1).

    # Days Offset calculation:
    # D1 -> 0
    # D8 -> 7
    # W6 -> (6-1)*7 = 35 days? Or just 6*7=42?
    # Usually W1 = Days 0-6 or 1-7.
    # Let's assume Wx = x * 7 days (approx) or start of that week.
    # User prompt: "From D1 is week 0".
    # D1 = Day 1.
    # D8 = Day 8.
    # W6 = Week 6. (Day 42 approx).

    # Let's use simple logic:
    # if 'D' in code: offset = int(code[1:]) - 1
    # if 'W' in code: offset = (int(code[1:]) * 7) - 1 # Start of that week? Or end?
    # Usually vaccination at "Week 6" means during week 6. Let's aim for start of week (Day 42).

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

    from datetime import timedelta

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
                # Week 6 starts at Day (6*7)-7+1 = 36?
                # Or Week 6 = 42 days?
                # Let's assume W6 = 42 days old (End of week 6/Start of week 7) or Start of Week 6 (Day 36).
                # User picture implies Age "Week 6". Let's stick to Week * 7 days.
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
    db.session.commit()

@app.route('/')
def index():
    active_flocks = Flock.query.filter_by(status='Active').all()

    # Enrich with today's status and cumulative mortality split
    today = date.today()
    for f in active_flocks:
        # Check if log exists for today
        log_today = DailyLog.query.filter_by(flock_id=f.id, date=today).first()
        f.has_log_today = True if log_today else False

        # Calculate Cumulative Mortality (Rearing vs Production)
        logs = DailyLog.query.filter_by(flock_id=f.id).order_by(DailyLog.date.asc()).all()

        rearing_mort_m = 0
        rearing_mort_f = 0
        prod_mort_m = 0
        prod_mort_f = 0

        prod_start_stock_m = f.intake_male
        prod_start_stock_f = f.intake_female

        # Determine Production Start
        # Priority: Explicit Date -> First Egg -> Manual Phase Switch (Not tracked historically easily)
        prod_start_date = f.production_start_date

        # Stock Tracking
        curr_m_prod = f.intake_male
        curr_m_hosp = 0
        curr_f = f.intake_female

        # Flag to indicate if we have reached production phase in the loop
        in_production = False

        for l in logs:
            # Check Phase Transition
            if not in_production:
                if prod_start_date and l.date >= prod_start_date:
                    in_production = True
                    prod_start_stock_m = curr_m_prod # Snapshot at start of prod
                    prod_start_stock_f = curr_f
                elif not prod_start_date and l.eggs_collected > 0:
                     # Fallback: First egg triggers production stats if no date set
                    in_production = True
                    prod_start_stock_m = curr_m_prod
                    prod_start_stock_f = curr_f

            # Cumulative Mortality/Culls calculation
            if in_production:
                prod_mort_m += l.mortality_male
                prod_mort_f += l.mortality_female
            else:
                rearing_mort_m += l.mortality_male
                rearing_mort_f += l.mortality_female

            # Update Stocks
            # Prod Stock = Previous Prod - Prod Mort - Prod Culls - Moved to Hosp + Moved to Prod
            # Hosp Stock = Previous Hosp - Hosp Mort - Hosp Culls + Moved to Hosp - Moved to Prod

            mort_m_prod = l.mortality_male
            mort_m_hosp = l.mortality_male_hosp or 0

            cull_m_prod = l.culls_male
            cull_m_hosp = l.culls_male_hosp or 0

            moved_to_hosp = l.males_moved_to_hosp or 0
            moved_to_prod = l.males_moved_to_prod or 0

            curr_m_prod = curr_m_prod - mort_m_prod - cull_m_prod - moved_to_hosp + moved_to_prod
            curr_m_hosp = curr_m_hosp - mort_m_hosp - cull_m_hosp + moved_to_hosp - moved_to_prod

            # Ensure no negative stock (safety)
            if curr_m_prod < 0: curr_m_prod = 0
            if curr_m_hosp < 0: curr_m_hosp = 0

            curr_f -= (l.mortality_female + l.culls_female)
            if curr_f < 0: curr_f = 0

        f.rearing_mort_m_pct = (rearing_mort_m / f.intake_male * 100) if f.intake_male else 0
        f.rearing_mort_f_pct = (rearing_mort_f / f.intake_female * 100) if f.intake_female else 0

        f.prod_mort_m_pct = (prod_mort_m / prod_start_stock_m * 100) if prod_start_stock_m else 0
        f.prod_mort_f_pct = (prod_mort_f / prod_start_stock_f * 100) if prod_start_stock_f else 0

        # Male Ratio (Current)
        # Ratio = Males in Prod / Females * 100
        f.male_ratio_pct = (curr_m_prod / curr_f * 100) if curr_f > 0 else 0
        f.males_prod_count = curr_m_prod
        f.males_hosp_count = curr_m_hosp

        # Current Week
        days_age = (today - f.intake_date).days
        f.current_week = (days_age // 7) + 1 if days_age >= 0 else 0

    return render_template('index.html', active_flocks=active_flocks, today=today)

@app.route('/flock/<int:id>/edit', methods=['GET', 'POST'])
def edit_flock(id):
    flock = Flock.query.get_or_404(id)
    if request.method == 'POST':
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
        flash(f'Flock {flock.batch_id} updated.', 'success')
        return redirect(url_for('index'))

    return render_template('flock_edit.html', flock=flock)

@app.route('/flock/<int:id>/delete', methods=['POST'])
def delete_flock(id):
    flock = Flock.query.get_or_404(id)
    # SQLAlchemy relationship handles cascade delete for logs, sampling events, vaccines, etc.
    db.session.delete(flock)
    db.session.commit()
    flash(f'Flock {flock.batch_id} deleted.', 'warning')
    return redirect(url_for('index'))

@app.route('/help')
def help():
    return render_template('help.html')

@app.route('/flocks', methods=['GET', 'POST'])
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
            flash(f'Error: House {house.name} already has an active flock (Batch: {existing_active.batch_id})', 'danger')
            return redirect(url_for('manage_flocks'))
        
        # Generate Batch ID
        intake_date = datetime.strptime(intake_date_str, '%Y-%m-%d').date()
        date_str = intake_date.strftime('%y%m%d')
        
        # Calculate N (Total flocks for this house + 1)
        house_flock_count = Flock.query.filter_by(house_id=house.id).count()
        n = house_flock_count + 1
        
        batch_id = f"{house.name}_{date_str}_Batch{n}"
        
        new_flock = Flock(
            house_id=house.id,
            batch_id=batch_id,
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

        flash(f'Flock created successfully! Batch ID: {batch_id}', 'success')
        return redirect(url_for('index'))
    
    houses = House.query.all()
    flocks = Flock.query.order_by(Flock.intake_date.desc()).all()
    return render_template('flock_form.html', houses=houses, flocks=flocks)

@app.route('/flock/<int:id>/close', methods=['POST'])
def close_flock(id):
    flock = Flock.query.get_or_404(id)
    flock.status = 'Inactive'
    flock.end_date = date.today()
    db.session.commit()
    flash(f'Flock {flock.batch_id} closed.', 'info')
    return redirect(url_for('index'))

@app.route('/standards', methods=['GET', 'POST'])
def manage_standards():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            s = Standard(
                week=int(request.form.get('week')),
                std_mortality_male=float(request.form.get('std_mortality_male') or 0),
                std_mortality_female=float(request.form.get('std_mortality_female') or 0),
                std_bw_male=float(request.form.get('std_bw_male') or 0),
                std_bw_female=float(request.form.get('std_bw_female') or 0),
                std_egg_prod=float(request.form.get('std_egg_prod') or 0)
            )
            db.session.add(s)
            db.session.commit()
            flash('Standard added.', 'success')

        # Could handle delete/update here

        return redirect(url_for('manage_standards'))

    standards = Standard.query.order_by(Standard.week.asc()).all()
    return render_template('standards.html', standards=standards)

@app.route('/feed_codes', methods=['GET', 'POST'])
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

    # Seed if empty
    if FeedCode.query.count() == 0:
        default_codes = ['161C', '162C', '163C', '168C', '169C', '170P', '171P', '172P']
        for c in default_codes:
            db.session.add(FeedCode(code=c))
        db.session.commit()

    codes = FeedCode.query.order_by(FeedCode.code.asc()).all()
    return render_template('feed_codes.html', codes=codes)

@app.route('/feed_codes/delete/<int:id>', methods=['POST'])
def delete_feed_code(id):
    fc = FeedCode.query.get_or_404(id)
    db.session.delete(fc)
    db.session.commit()
    flash(f'Feed Code {fc.code} deleted.', 'info')
    return redirect(url_for('manage_feed_codes'))

@app.route('/api/chart_data/<int:flock_id>')
def get_chart_data(flock_id):
    flock = Flock.query.get_or_404(flock_id)

    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    mode = request.args.get('mode', 'daily') # 'daily', 'weekly', 'monthly'

    # Pre-calculate stocks for %
    cum_mort_m = 0
    cum_mort_f = 0
    cum_cull_m = 0
    cum_cull_f = 0
    start_m = flock.intake_male or 1
    start_f = flock.intake_female or 1

    all_logs = DailyLog.query.filter_by(flock_id=flock_id).order_by(DailyLog.date.asc()).all()

    data = {
        'flock_batch': flock.batch_id,
        'intake_date': flock.intake_date.isoformat(),
        'dates': [],
        'weeks': [],
        'ranges': [], # New: Store {start, end} for each point for drill-down
        'metrics': {
            'mortality_f_pct': [], 'mortality_m_pct': [], # Depletion %
            'culls_f_pct': [], 'culls_m_pct': [],
            'egg_prod_pct': [], 'hatch_egg_pct': [],
            'bw_f': [], 'bw_m': [],
            'uni_f': [], 'uni_m': [],
            'feed_f': [], 'feed_m': [],
            'water_per_bird': [],
        },
        'events': []
    }

    weekly_agg = {}
    monthly_agg = {}

    for log in all_logs:
        curr_stock_m = start_m - cum_mort_m - cum_cull_m
        if curr_stock_m <= 0: curr_stock_m = 1
        curr_stock_f = start_f - cum_mort_f - cum_cull_f
        if curr_stock_f <= 0: curr_stock_f = 1

        # Calculate Daily Metrics
        daily_mort_f_pct = ((log.mortality_female + log.culls_female) / curr_stock_f) * 100
        daily_mort_m_pct = ((log.mortality_male + log.culls_male) / curr_stock_m) * 100

        egg_prod_pct = (log.eggs_collected / curr_stock_f) * 100

        total_cull_eggs = log.cull_eggs_jumbo + log.cull_eggs_small + log.cull_eggs_abnormal + log.cull_eggs_crack
        hatch_eggs = log.eggs_collected - total_cull_eggs
        hatch_pct = (hatch_eggs / log.eggs_collected * 100) if log.eggs_collected > 0 else 0

        water_per_bird_ml = (log.water_intake_calculated * 1000) / (curr_stock_m + curr_stock_f) if (curr_stock_m + curr_stock_f) > 0 else 0

        # Determine if in range
        in_range = True
        if start_date_str and log.date < datetime.strptime(start_date_str, '%Y-%m-%d').date(): in_range = False
        if end_date_str and log.date > datetime.strptime(end_date_str, '%Y-%m-%d').date(): in_range = False

        if mode == 'daily' and in_range:
            data['dates'].append(log.date.isoformat())
            data['metrics']['mortality_f_pct'].append(round(daily_mort_f_pct, 2))
            data['metrics']['mortality_m_pct'].append(round(daily_mort_m_pct, 2))
            data['metrics']['egg_prod_pct'].append(round(egg_prod_pct, 2))
            data['metrics']['hatch_egg_pct'].append(round(hatch_pct, 2))
            data['metrics']['bw_f'].append(log.body_weight_female)
            data['metrics']['bw_m'].append(log.body_weight_male)
            data['metrics']['uni_f'].append(log.uniformity_female)
            data['metrics']['uni_m'].append(log.uniformity_male)
            data['metrics']['feed_f'].append(log.feed_female_gp_bird)
            data['metrics']['feed_m'].append(log.feed_male_gp_bird)
            data['metrics']['water_per_bird'].append(round(water_per_bird_ml, 1))

            if log.photo_path or log.clinical_notes or log.flushing:
                note = log.clinical_notes or ""
                if log.flushing:
                    note = f"[FLUSHING] {note}"

                data['events'].append({
                    'date': log.date.isoformat(),
                    'note': note.strip(),
                    'photo': url_for('uploaded_file', filename=os.path.basename(log.photo_path)) if log.photo_path else None,
                    'type': 'flushing' if log.flushing else 'note'
                })

        # Update Cumulatives for next iteration
        cum_mort_m += log.mortality_male
        cum_mort_f += log.mortality_female
        cum_cull_m += log.culls_male
        cum_cull_f += log.culls_female

        # Aggregate Weekly (Collect regardless of filter to ensure accurate sums within week)
        days_diff = (log.date - flock.intake_date).days
        week_num = (days_diff // 7) + 1

        if week_num not in weekly_agg:
            weekly_agg[week_num] = {
                'count': 0,
                'mort_f_sum': 0, 'mort_m_sum': 0,
                'cull_f_sum': 0, 'cull_m_sum': 0,
                'eggs_sum': 0, 'hatch_eggs_sum': 0,
                'bw_f_sum': 0, 'bw_f_count': 0,
                'bw_m_sum': 0, 'bw_m_count': 0,
                'uni_f_sum': 0, 'uni_f_count': 0,
                'uni_m_sum': 0, 'uni_m_count': 0,
                'feed_f_sum': 0, 'feed_m_sum': 0,
                'water_vol_sum': 0,
                'stock_f_start': curr_stock_f, # Approximation for start of week logic if needed
                'stock_m_start': curr_stock_m,
                'date_start': log.date,
                'date_end': log.date
            }

        w = weekly_agg[week_num]
        w['count'] += 1
        w['date_end'] = log.date
        w['mort_f_sum'] += log.mortality_female
        w['mort_m_sum'] += log.mortality_male
        w['cull_f_sum'] += log.culls_female
        w['cull_m_sum'] += log.culls_male
        w['eggs_sum'] += log.eggs_collected
        w['hatch_eggs_sum'] += hatch_eggs
        w['water_vol_sum'] += log.water_intake_calculated # Liters

        if log.body_weight_female > 0:
            w['bw_f_sum'] += log.body_weight_female
            w['bw_f_count'] += 1
        if log.body_weight_male > 0:
            w['bw_m_sum'] += log.body_weight_male
            w['bw_m_count'] += 1

        if log.uniformity_female > 0:
            w['uni_f_sum'] += log.uniformity_female
            w['uni_f_count'] += 1
        if log.uniformity_male > 0:
            w['uni_m_sum'] += log.uniformity_male
            w['uni_m_count'] += 1

        w['feed_f_sum'] += log.feed_female_gp_bird
        w['feed_m_sum'] += log.feed_male_gp_bird

        # Aggregate Monthly
        month_key = log.date.strftime('%Y-%m')
        if month_key not in monthly_agg:
            monthly_agg[month_key] = {
                'count': 0,
                'mort_f_sum': 0, 'mort_m_sum': 0,
                'cull_f_sum': 0, 'cull_m_sum': 0,
                'eggs_sum': 0, 'hatch_eggs_sum': 0,
                'bw_f_sum': 0, 'bw_f_count': 0,
                'bw_m_sum': 0, 'bw_m_count': 0,
                'uni_f_sum': 0, 'uni_f_count': 0,
                'uni_m_sum': 0, 'uni_m_count': 0,
                'feed_f_sum': 0, 'feed_m_sum': 0,
                'water_vol_sum': 0,
                'stock_f_start': curr_stock_f,
                'stock_m_start': curr_stock_m,
                'date_start': log.date,
                'date_end': log.date
            }

        m = monthly_agg[month_key]
        m['count'] += 1
        m['date_end'] = log.date # update to max date
        m['mort_f_sum'] += log.mortality_female
        m['mort_m_sum'] += log.mortality_male
        m['cull_f_sum'] += log.culls_female
        m['cull_m_sum'] += log.culls_male
        m['eggs_sum'] += log.eggs_collected
        m['hatch_eggs_sum'] += hatch_eggs
        m['water_vol_sum'] += log.water_intake_calculated # Liters

        if log.body_weight_female > 0:
            m['bw_f_sum'] += log.body_weight_female
            m['bw_f_count'] += 1
        if log.body_weight_male > 0:
            m['bw_m_sum'] += log.body_weight_male
            m['bw_m_count'] += 1

        if log.uniformity_female > 0:
            m['uni_f_sum'] += log.uniformity_female
            m['uni_f_count'] += 1
        if log.uniformity_male > 0:
            m['uni_m_sum'] += log.uniformity_male
            m['uni_m_count'] += 1

        m['feed_f_sum'] += log.feed_female_gp_bird
        m['feed_m_sum'] += log.feed_male_gp_bird

    # Process Aggregates based on Mode
    agg_data = None
    if mode == 'weekly':
        agg_data = weekly_agg
        label_prefix = "Week "
    elif mode == 'monthly':
        agg_data = monthly_agg
        label_prefix = ""

    if agg_data:
        sorted_keys = sorted(agg_data.keys())
        for k in sorted_keys:
            a = agg_data[k]

            # Filter check
            if start_date_str and a['date_end'] < datetime.strptime(start_date_str, '%Y-%m-%d').date(): continue
            if end_date_str and a['date_start'] > datetime.strptime(end_date_str, '%Y-%m-%d').date(): continue

            if mode == 'weekly':
                data['weeks'].append(k)

            data['dates'].append(f"{label_prefix}{k}")
            data['ranges'].append({'start': a['date_start'].isoformat(), 'end': a['date_end'].isoformat()})

            # Calculate Averages/Rates
            mort_f_pct = ((a['mort_f_sum'] + a['cull_f_sum']) / a['stock_f_start'] * 100) if a['stock_f_start'] > 0 else 0
            mort_m_pct = ((a['mort_m_sum'] + a['cull_m_sum']) / a['stock_m_start'] * 100) if a['stock_m_start'] > 0 else 0

            avg_stock_f = a['stock_f_start'] - ((a['mort_f_sum'] + a['cull_f_sum']) / 2)
            egg_prod_pct = (a['eggs_sum'] / (avg_stock_f * a['count'])) * 100 if (avg_stock_f * a['count']) > 0 else 0

            hatch_pct = (a['hatch_eggs_sum'] / a['eggs_sum'] * 100) if a['eggs_sum'] > 0 else 0

            avg_bw_f = a['bw_f_sum'] / a['bw_f_count'] if a['bw_f_count'] > 0 else 0
            avg_bw_m = a['bw_m_sum'] / a['bw_m_count'] if a['bw_m_count'] > 0 else 0
            avg_uni_f = a['uni_f_sum'] / a['uni_f_count'] if a['uni_f_count'] > 0 else 0
            avg_uni_m = a['uni_m_sum'] / a['uni_m_count'] if a['uni_m_count'] > 0 else 0

            avg_feed_f = a['feed_f_sum'] / a['count'] if a['count'] > 0 else 0
            avg_feed_m = a['feed_m_sum'] / a['count'] if a['count'] > 0 else 0

            avg_stock_total = avg_stock_f + (a['stock_m_start'] - ((a['mort_m_sum'] + a['cull_m_sum'])/2))
            water_ml_bird = (a['water_vol_sum'] * 1000) / (avg_stock_total * a['count']) if (avg_stock_total * a['count']) > 0 else 0

            data['metrics']['mortality_f_pct'].append(round(mort_f_pct, 2))
            data['metrics']['mortality_m_pct'].append(round(mort_m_pct, 2))
            data['metrics']['egg_prod_pct'].append(round(egg_prod_pct, 2))
            data['metrics']['hatch_egg_pct'].append(round(hatch_pct, 2))
            data['metrics']['bw_f'].append(round(avg_bw_f, 2))
            data['metrics']['bw_m'].append(round(avg_bw_m, 2))
            data['metrics']['uni_f'].append(round(avg_uni_f, 2))
            data['metrics']['uni_m'].append(round(avg_uni_m, 2))
            data['metrics']['feed_f'].append(round(avg_feed_f, 2))
            data['metrics']['feed_m'].append(round(avg_feed_m, 2))
            data['metrics']['water_per_bird'].append(round(water_ml_bird, 1))

    return data

@app.route('/flock/<int:id>/toggle_phase', methods=['POST'])
def toggle_phase(id):
    flock = Flock.query.get_or_404(id)
    if flock.phase == 'Rearing':
        flock.phase = 'Production'

        prod_date_str = request.form.get('production_start_date')
        if prod_date_str:
            flock.production_start_date = datetime.strptime(prod_date_str, '%Y-%m-%d').date()
        else:
            flock.production_start_date = date.today()

        flash(f'Flock {flock.batch_id} switched to Production phase starting {flock.production_start_date}.', 'success')
    else:
        flock.phase = 'Rearing'
        flock.production_start_date = None
        flash(f'Flock {flock.batch_id} switched back to Rearing phase.', 'warning')
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/flock/<int:id>')
def view_flock(id):
    flock = Flock.query.get_or_404(id)
    logs = DailyLog.query.filter_by(flock_id=id).order_by(DailyLog.date.asc()).all()
    
    # Calculate Weekly Summaries
    weekly_data = []
    current_week = None
    week_summary = None
    
    # Iterate sorted by date ASC
    for log in logs:
        # Determine Age in days (assuming intake_date is day 0 or 1?)
        # Excel template uses Age. Usually Age = (Date - IntakeDate).days
        days_diff = (log.date - flock.intake_date).days
        # Week number for summary (1-based index of weeks)
        week_num = (days_diff // 7) + 1
        
        if current_week != week_num:
            # Save previous week
            if week_summary:
                weekly_data.append(week_summary)
            
            # Start new week
            current_week = week_num
            week_summary = {
                'week': week_num,
                'mortality_male': 0, 'mortality_female': 0,
                'culls_male': 0, 'culls_female': 0,
                'feed_male_total': 0.0, 'feed_female_total': 0.0,
                'eggs': 0,
                'bw_male_sum': 0.0, 'bw_male_count': 0,
                'bw_female_sum': 0.0, 'bw_female_count': 0
            }
        
        week_summary['mortality_male'] += log.mortality_male
        week_summary['mortality_female'] += log.mortality_female
        week_summary['culls_male'] += log.culls_male
        week_summary['culls_female'] += log.culls_female
        week_summary['eggs'] += log.eggs_collected
        
        if log.body_weight_male > 0:
            week_summary['bw_male_sum'] += log.body_weight_male
            week_summary['bw_male_count'] += 1
        if log.body_weight_female > 0:
            week_summary['bw_female_sum'] += log.body_weight_female
            week_summary['bw_female_count'] += 1
            
    if week_summary:
        weekly_data.append(week_summary)
    
    # Calculate Averages
    for w in weekly_data:
        w['avg_bw_male'] = w['bw_male_sum'] / w['bw_male_count'] if w['bw_male_count'] > 0 else 0
        w['avg_bw_female'] = w['bw_female_sum'] / w['bw_female_count'] if w['bw_female_count'] > 0 else 0

    # Prepare Chart Data
    chart_data = {
        'dates': [log.date.strftime('%Y-%m-%d') for log in logs],
        'mortality_cum_male': [],
        'mortality_cum_female': [],
        'egg_prod': [],
        'bw_male_p1': [], 'bw_male_p2': [], 'bw_male_std': [],
        'bw_female_p1': [], 'bw_female_p2': [], 'bw_female_p3': [], 'bw_female_p4': [], 'bw_female_std': [],
        'unif_male': [], 'unif_female': []
    }
    
    # Calculate cumulative mortality and stock
    cum_mort_m = 0
    cum_mort_f = 0
    cum_cull_m = 0
    cum_cull_f = 0

    start_m = flock.intake_male or 1
    start_f = flock.intake_female or 1
    
    for log in logs:
        cum_mort_m += log.mortality_male
        cum_mort_f += log.mortality_female
        cum_cull_m += log.culls_male
        cum_cull_f += log.culls_female

        current_stock_f = start_f - cum_mort_f - cum_cull_f
        if current_stock_f <= 0: current_stock_f = 1
        
        chart_data['mortality_cum_male'].append(round((cum_mort_m / start_m) * 100, 2))
        chart_data['mortality_cum_female'].append(round((cum_mort_f / start_f) * 100, 2))
        
        egg_prod = (log.eggs_collected / current_stock_f) * 100
        chart_data['egg_prod'].append(round(egg_prod, 2))

        # Partitions or Null if 0 (to break lines)
        def val_or_null(v):
            return v if v > 0 else None

        chart_data['bw_male_p1'].append(val_or_null(log.bw_male_p1))
        chart_data['bw_male_p2'].append(val_or_null(log.bw_male_p2))
        chart_data['bw_male_std'].append(val_or_null(log.standard_bw_male))

        chart_data['bw_female_p1'].append(val_or_null(log.bw_female_p1))
        chart_data['bw_female_p2'].append(val_or_null(log.bw_female_p2))
        chart_data['bw_female_p3'].append(val_or_null(log.bw_female_p3))
        chart_data['bw_female_p4'].append(val_or_null(log.bw_female_p4))
        chart_data['bw_female_std'].append(val_or_null(log.standard_bw_female))

        # Dynamic Partitions (M1-M8, F1-F8)
        p_map = {pw.partition_name: pw.body_weight for pw in log.partition_weights}

        for i in range(1, 9):
            key_m = f'bw_M{i}'
            key_f = f'bw_F{i}'
            if key_m not in chart_data: chart_data[key_m] = []
            if key_f not in chart_data: chart_data[key_f] = []

            val_m = p_map.get(f'M{i}', 0)
            # Fallback to legacy columns for M1, M2
            if val_m == 0 and i <= 2:
                val_m = getattr(log, f'bw_male_p{i}', 0)

            val_f = p_map.get(f'F{i}', 0)
            # Fallback to legacy columns for F1-F4
            if val_f == 0 and i <= 4:
                val_f = getattr(log, f'bw_female_p{i}', 0)

            chart_data[key_m].append(val_or_null(val_m))
            chart_data[key_f].append(val_or_null(val_f))

        chart_data['unif_male'].append(val_or_null(log.uniformity_male))
        chart_data['unif_female'].append(val_or_null(log.uniformity_female))

    return render_template('flock_detail.html', flock=flock, logs=list(reversed(logs)), weekly_data=weekly_data, chart_data=chart_data)

@app.route('/flock/<int:id>/charts')
def flock_charts(id):
    flock = Flock.query.get_or_404(id)
    return render_template('flock_charts.html', flock=flock)

@app.route('/flock/<int:id>/sampling')
def flock_sampling(id):
    flock = Flock.query.get_or_404(id)
    events = SamplingEvent.query.filter_by(flock_id=id).order_by(SamplingEvent.age_week.asc()).all()
    return render_template('flock_sampling.html', flock=flock, events=events)

@app.route('/flock/<int:id>/vaccines', methods=['GET', 'POST'])
def flock_vaccines(id):
    flock = Flock.query.get_or_404(id)
    if request.method == 'POST':
        vaccine_id = request.form.get('vaccine_id')
        v = Vaccine.query.get_or_404(vaccine_id)

        actual_date_str = request.form.get('actual_date')
        if actual_date_str:
            v.actual_date = datetime.strptime(actual_date_str, '%Y-%m-%d').date()

        # Remarks update
        remarks = request.form.get('remarks')
        if remarks is not None:
             v.remarks = remarks

        db.session.commit()
        flash('Vaccine record updated.', 'success')
        return redirect(url_for('flock_vaccines', id=id))

    vaccines = Vaccine.query.filter_by(flock_id=id).order_by(Vaccine.id.asc()).all()
    return render_template('flock_vaccines.html', flock=flock, vaccines=vaccines)

@app.route('/vaccine_schedule')
def global_vaccine_schedule():
    # Show monthly schedule for all active flocks
    active_flocks = Flock.query.filter_by(status='Active').all()
    flock_ids = [f.id for f in active_flocks]

    # Get all pending vaccines or vaccines in future?
    # "Show monthly what vaccine is needed"
    vaccines = Vaccine.query.filter(Vaccine.flock_id.in_(flock_ids)).order_by(Vaccine.est_date.asc()).all()

    # Group by Month
    schedule = {}

    for v in vaccines:
        if not v.est_date: continue
        month_key = v.est_date.strftime('%Y-%m') # "2024-05"
        if month_key not in schedule:
            schedule[month_key] = []
        schedule[month_key].append(v)

    return render_template('vaccine_schedule.html', schedule=schedule)

@app.route('/flock/<int:id>/sampling/<int:event_id>/upload', methods=['POST'])
def upload_sampling_result(id, event_id):
    event = SamplingEvent.query.get_or_404(event_id)

    # Update Remarks regardless of file? Or only with file?
    # Usually we upload file OR just mark complete/add remarks.
    # User said "upload and keep sampling result".
    # I'll allow updating remarks even if no file is uploaded, but status might depend on file.

    remarks = request.form.get('remarks')
    if remarks:
        event.remarks = remarks

    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename != '':
            if file.filename.lower().endswith('.pdf'):
                filename = secure_filename(f"{event.flock.batch_id}_W{event.age_week}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                event.result_file = filepath
                event.upload_date = date.today()
                event.status = 'Completed'
                db.session.commit()
                flash('Result uploaded successfully.', 'success')
            else:
                flash('Only PDF files are allowed.', 'danger')

    # If just remarks updated
    if remarks and not ('file' in request.files and request.files['file'].filename != ''):
        db.session.commit()
        flash('Remarks updated.', 'success')

    return redirect(url_for('flock_sampling', id=id))

@app.route('/flock/<int:id>/dashboard')
def flock_dashboard(id):
    flock = Flock.query.get_or_404(id)

    date_str = request.args.get('date')
    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = date.today()

    # Get Logs
    log_today = DailyLog.query.filter_by(flock_id=id, date=target_date).first()

    from datetime import timedelta
    log_prev = DailyLog.query.filter_by(flock_id=id, date=target_date - timedelta(days=1)).first()

    # Calculate Age
    age_days = (target_date - flock.intake_date).days
    age_week = (age_days // 7) + 1

    # Fetch Standard for this week
    standard = Standard.query.filter_by(week=age_week).first()

    # Pre-calc cumulatives for KPI
    # We need cumulative up to today
    all_logs = DailyLog.query.filter_by(flock_id=id).filter(DailyLog.date <= target_date).order_by(DailyLog.date.asc()).all()

    cum_mort_m = 0
    cum_mort_f = 0
    cum_cull_m = 0
    cum_cull_f = 0

    start_m = flock.intake_male
    start_f = flock.intake_female

    for l in all_logs:
        cum_mort_m += l.mortality_male
        cum_mort_f += l.mortality_female
        cum_cull_m += l.culls_male
        cum_cull_f += l.culls_female

    curr_stock_m = start_m - cum_mort_m - cum_cull_m
    curr_stock_f = start_f - cum_mort_f - cum_cull_f
    if curr_stock_m <= 0: curr_stock_m = 1
    if curr_stock_f <= 0: curr_stock_f = 1

    # Prepare KPI Data Structure
    kpis = []

    def get_val(log, attr, default=0):
        return getattr(log, attr) if log else default

    def calc_pct(num, den):
        return (num / den * 100) if den > 0 else 0

    # 1. Female Mortality % (Daily)
    mort_f_val = calc_pct(get_val(log_today, 'mortality_female'), curr_stock_f)
    mort_f_prev = calc_pct(get_val(log_prev, 'mortality_female'), curr_stock_f + get_val(log_today, 'mortality_female')) # Approx prev stock

    std_mort_f = standard.std_mortality_female if standard else None

    kpis.append({
        'label': 'Female Mortality %',
        'value': mort_f_val,
        'prev': mort_f_prev,
        'unit': '%',
        'std': std_mort_f,
        'reverse_bad': True # Higher is bad
    })

    # 2. Female Cull %
    cull_f_val = calc_pct(get_val(log_today, 'culls_female'), curr_stock_f)
    cull_f_prev = calc_pct(get_val(log_prev, 'culls_female'), curr_stock_f)
    kpis.append({
        'label': 'Female Cull %',
        'value': cull_f_val,
        'prev': cull_f_prev,
        'unit': '%',
        'std': None,
        'reverse_bad': True
    })

    # 3. Female Cum Mort %
    cum_mort_f_pct = calc_pct(cum_mort_f, start_f)
    # prev cum is cum - today's
    cum_mort_f_prev = calc_pct(cum_mort_f - get_val(log_today, 'mortality_female'), start_f)
    kpis.append({
        'label': 'Female Cum. Mort %',
        'value': cum_mort_f_pct,
        'prev': cum_mort_f_prev,
        'unit': '%',
        'std': None,
        'reverse_bad': True
    })

    # 4. Egg Prod %
    eggs = get_val(log_today, 'eggs_collected')
    egg_prod = calc_pct(eggs, curr_stock_f)
    eggs_prev = get_val(log_prev, 'eggs_collected')
    egg_prod_prev = calc_pct(eggs_prev, curr_stock_f) # approx stock

    std_egg = standard.std_egg_prod if standard else None
    kpis.append({
        'label': 'Egg Production %',
        'value': egg_prod,
        'prev': egg_prod_prev,
        'unit': '%',
        'std': std_egg,
        'reverse_bad': False # Lower is bad
    })

    # 5. Body Weights
    bw_f = get_val(log_today, 'body_weight_female')
    bw_f_prev = get_val(log_prev, 'body_weight_female')
    std_bw_f = standard.std_bw_female if standard else None
    kpis.append({
        'label': 'Female BW',
        'value': bw_f,
        'prev': bw_f_prev,
        'unit': 'g',
        'std': std_bw_f,
        'reverse_bad': False # Depends, but low is bad usually
    })

    # Calculate diff and status
    diagnostic_hints = []

    for k in kpis:
        k['diff'] = k['value'] - k['prev']
        k['status'] = 'neutral'

        std_val = k.get('std')
        if std_val is not None and k['value'] > 0:
            # Anomaly Detection Logic
            if k['reverse_bad']: # Higher than std is bad
                if k['value'] > std_val * 1.1: # 10% tolerance?
                    k['status'] = 'danger'
                    diagnostic_hints.append(f"Abnormal {k['label']}: Deviation > 10% from Standard.")
                elif k['value'] > std_val:
                    k['status'] = 'warning'
            else: # Lower than std is bad
                if k['value'] < std_val * 0.9:
                    k['status'] = 'danger'
                    diagnostic_hints.append(f"Abnormal {k['label']}: Deviation > 10% from Standard.")
                elif k['value'] < std_val:
                    k['status'] = 'warning'

    # Mortality Spike Rule: > 0.1% for 3 consecutive days
    # Need last 3 logs including target_date
    last_3_logs = DailyLog.query.filter_by(flock_id=id).filter(DailyLog.date <= target_date).order_by(DailyLog.date.desc()).limit(3).all()

    if len(last_3_logs) == 3:
        spike_count = 0
        temp_stock_f = curr_stock_f

        # logs[0] is Target Date
        # logs[1] is Target - 1
        # logs[2] is Target - 2

        # Check logs[0]
        m_pct = (last_3_logs[0].mortality_female / temp_stock_f * 100) if temp_stock_f > 0 else 0
        if m_pct > 0.1: spike_count += 1

        # Check logs[1]
        temp_stock_f += (last_3_logs[0].mortality_female + last_3_logs[0].culls_female)
        m_pct = (last_3_logs[1].mortality_female / temp_stock_f * 100) if temp_stock_f > 0 else 0
        if m_pct > 0.1: spike_count += 1

        # Check logs[2]
        temp_stock_f += (last_3_logs[1].mortality_female + last_3_logs[1].culls_female)
        m_pct = (last_3_logs[2].mortality_female / temp_stock_f * 100) if temp_stock_f > 0 else 0
        if m_pct > 0.1: spike_count += 1

        if spike_count == 3:
             diagnostic_hints.insert(0, "Warning: Continuous mortality spike—review post-mortem photos.")

    return render_template('flock_kpi.html', flock=flock, kpis=kpis, target_date=target_date, age_week=age_week, age_days=age_days, diagnostic_hints=diagnostic_hints)

@app.route('/daily_log', methods=['GET', 'POST'])
def daily_log():
    if request.method == 'POST':
        house_id = request.form.get('house_id')
        date_str = request.form.get('date')
        
        # Look up active flock for the house
        flock = Flock.query.filter_by(house_id=house_id, status='Active').first()
        if not flock:
            flash('Error: No active flock found for this house.', 'danger')
            return redirect(url_for('daily_log'))
        
        log_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Handle File Upload
        photo_path = None
        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename != '':
                raw_name = f"{flock.batch_id}_{date_str}_{file.filename}"
                filename = secure_filename(raw_name)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                photo_path = filepath
        
        # Water Calculation
        water_r1 = int(request.form.get('water_reading_1') or 0)
        water_r3 = int(request.form.get('water_reading_3') or 0)
        
        # Calculate 24h intake: (R1_today - R1_yesterday) * 1000/100
        # Find yesterday's log
        from datetime import timedelta
        yesterday = log_date - timedelta(days=1)
        yesterday_log = DailyLog.query.filter_by(flock_id=flock.id, date=yesterday).first()
        
        water_intake_calc = 0.0
        if yesterday_log:
            r1_today_real = water_r1 / 100.0
            r1_yesterday_real = yesterday_log.water_reading_1 / 100.0
            water_intake_calc = (r1_today_real - r1_yesterday_real) * 1000.0

        # Prepare Body Weight Data
        bw_m_val = float(request.form.get('body_weight_male') or 0)
        bw_f_val = float(request.form.get('body_weight_female') or 0)
        uni_m_val = float(request.form.get('uniformity_male') or 0)
        uni_f_val = float(request.form.get('uniformity_female') or 0)

        # Rearing Phase Partition Logic
        partition_data = []
        if flock.phase == 'Rearing':
            # Collect Partitions - Dynamic M1-M8, F1-F8
            f_parts = [f'F{i}' for i in range(1, 9)]
            m_parts = [f'M{i}' for i in range(1, 9)]

            sum_bw_f = 0
            count_bw_f = 0
            sum_uni_f = 0
            count_uni_f = 0

            sum_bw_m = 0
            count_bw_m = 0
            sum_uni_m = 0
            count_uni_m = 0

            # Process Female
            for p in f_parts:
                bw = float(request.form.get(f'bw_{p}') or 0)
                uni = float(request.form.get(f'uni_{p}') or 0)
                if bw > 0:
                    partition_data.append({'name': p, 'bw': bw, 'uni': uni})
                    sum_bw_f += bw
                    count_bw_f += 1
                    if uni > 0:
                        sum_uni_f += uni
                        count_uni_f += 1

            # Process Male
            for p in m_parts:
                bw = float(request.form.get(f'bw_{p}') or 0)
                uni = float(request.form.get(f'uni_{p}') or 0)
                if bw > 0:
                    partition_data.append({'name': p, 'bw': bw, 'uni': uni})
                    sum_bw_m += bw
                    count_bw_m += 1
                    if uni > 0:
                        sum_uni_m += uni
                        count_uni_m += 1

            # Calculate Averages (Overwrite manual if partitions exist)
            if count_bw_f > 0:
                bw_f_val = sum_bw_f / count_bw_f
            if count_uni_f > 0:
                uni_f_val = sum_uni_f / count_uni_f

            if count_bw_m > 0:
                bw_m_val = sum_bw_m / count_bw_m
            if count_uni_m > 0:
                uni_m_val = sum_uni_m / count_uni_m

        is_weighing = 'is_weighing_day' in request.form

        new_log = DailyLog(
            flock_id=flock.id,
            date=log_date,
            mortality_male=int(request.form.get('mortality_male') or 0),
            mortality_female=int(request.form.get('mortality_female') or 0),

            mortality_male_hosp=int(request.form.get('mortality_male_hosp') or 0),
            culls_male_hosp=int(request.form.get('culls_male_hosp') or 0),

            culls_male=int(request.form.get('culls_male') or 0),
            culls_female=int(request.form.get('culls_female') or 0),

            males_moved_to_prod=int(request.form.get('males_moved_to_prod') or 0),
            males_moved_to_hosp=int(request.form.get('males_moved_to_hosp') or 0),

            feed_program=request.form.get('feed_program'),
            feed_code_id=int(request.form.get('feed_code_id')) if request.form.get('feed_code_id') else None,
            
            feed_male_gp_bird=float(request.form.get('feed_male_gp_bird') or 0),
            feed_female_gp_bird=float(request.form.get('feed_female_gp_bird') or 0),
            
            eggs_collected=int(request.form.get('eggs_collected') or 0),
            cull_eggs_jumbo=int(request.form.get('cull_eggs_jumbo') or 0),
            cull_eggs_small=int(request.form.get('cull_eggs_small') or 0),
            cull_eggs_abnormal=int(request.form.get('cull_eggs_abnormal') or 0),
            cull_eggs_crack=int(request.form.get('cull_eggs_crack') or 0),
            egg_weight=float(request.form.get('egg_weight') or 0),
            
            body_weight_male=bw_m_val,
            body_weight_female=bw_f_val,
            uniformity_male=uni_m_val,
            uniformity_female=uni_f_val,
            
            is_weighing_day=is_weighing,
            bw_male_p1=float(request.form.get('bw_M1') or 0),
            bw_male_p2=float(request.form.get('bw_M2') or 0),
            unif_male_p1=float(request.form.get('uni_M1') or 0),
            unif_male_p2=float(request.form.get('uni_M2') or 0),
            bw_female_p1=float(request.form.get('bw_F1') or 0),
            bw_female_p2=float(request.form.get('bw_F2') or 0),
            bw_female_p3=float(request.form.get('bw_F3') or 0),
            bw_female_p4=float(request.form.get('bw_F4') or 0),
            unif_female_p1=float(request.form.get('uni_F1') or 0),
            unif_female_p2=float(request.form.get('uni_F2') or 0),
            unif_female_p3=float(request.form.get('uni_F3') or 0),
            unif_female_p4=float(request.form.get('uni_F4') or 0),
            standard_bw_male=float(request.form.get('standard_bw_male') or 0),
            standard_bw_female=float(request.form.get('standard_bw_female') or 0),

            water_reading_1=water_r1,
            water_reading_2=int(request.form.get('water_reading_2') or 0),
            water_reading_3=water_r3,
            water_intake_calculated=water_intake_calc,
            flushing=True if request.form.get('flushing') else False,
            
            light_on_time=request.form.get('light_on_time'),
            light_off_time=request.form.get('light_off_time'),
            feed_cleanup_start=request.form.get('feed_cleanup_start'),
            feed_cleanup_end=request.form.get('feed_cleanup_end'),
            
            clinical_notes=request.form.get('clinical_notes'),
            photo_path=photo_path
        )
        
        db.session.add(new_log)
        db.session.commit()

        # Save Partitions
        for p in partition_data:
            pw = PartitionWeight(
                log_id=new_log.id,
                partition_name=p['name'],
                body_weight=p['bw'],
                uniformity=p['uni']
            )
            db.session.add(pw)
        db.session.commit()
        flash('Daily Log submitted successfully!', 'success')
        return redirect(url_for('index'))
        
    # GET: Only show houses with Active flocks
    active_flocks = Flock.query.filter_by(status='Active').all()
    active_houses = [f.house for f in active_flocks]

    # Map House ID to Phase
    import json
    flock_phases = {f.house_id: f.phase for f in active_flocks}

    feed_codes = FeedCode.query.order_by(FeedCode.code.asc()).all()

    return render_template('daily_log_form.html', houses=active_houses, flock_phases_json=json.dumps(flock_phases), feed_codes=feed_codes)

@app.context_processor
def utility_processor():
    def get_partition_val(log, name, type_):
        if not log: return 0.0
        # Check pre-loaded relationship or query
        # Since we use lazy=True, accessing log.partition_weights triggers query
        for pw in log.partition_weights:
            if pw.partition_name == name:
                return pw.body_weight if type_ == 'bw' else pw.uniformity
        return 0.0
    return dict(get_partition_val=get_partition_val)

@app.route('/daily_log/<int:id>/edit', methods=['GET', 'POST'])
def edit_daily_log(id):
    log = DailyLog.query.get_or_404(id)
    
    if request.method == 'POST':
        # Update fields
        log.mortality_male = int(request.form.get('mortality_male') or 0)
        log.mortality_female = int(request.form.get('mortality_female') or 0)

        log.mortality_male_hosp = int(request.form.get('mortality_male_hosp') or 0)
        log.culls_male_hosp = int(request.form.get('culls_male_hosp') or 0)

        log.culls_male = int(request.form.get('culls_male') or 0)
        log.culls_female = int(request.form.get('culls_female') or 0)

        log.males_moved_to_prod = int(request.form.get('males_moved_to_prod') or 0)
        log.males_moved_to_hosp = int(request.form.get('males_moved_to_hosp') or 0)

        log.feed_program = request.form.get('feed_program')
        log.feed_code_id = int(request.form.get('feed_code_id')) if request.form.get('feed_code_id') else None

        log.feed_male_gp_bird = float(request.form.get('feed_male_gp_bird') or 0)
        log.feed_female_gp_bird = float(request.form.get('feed_female_gp_bird') or 0)
        
        log.eggs_collected = int(request.form.get('eggs_collected') or 0)
        log.cull_eggs_jumbo = int(request.form.get('cull_eggs_jumbo') or 0)
        log.cull_eggs_small = int(request.form.get('cull_eggs_small') or 0)
        log.cull_eggs_abnormal = int(request.form.get('cull_eggs_abnormal') or 0)
        log.cull_eggs_crack = int(request.form.get('cull_eggs_crack') or 0)
        log.egg_weight = float(request.form.get('egg_weight') or 0)
        
        # Body Weight Logic (Handle Partitions on Edit)
        bw_m_val = float(request.form.get('body_weight_male') or 0)
        bw_f_val = float(request.form.get('body_weight_female') or 0)
        uni_m_val = float(request.form.get('uniformity_male') or 0)
        uni_f_val = float(request.form.get('uniformity_female') or 0)

        if log.flock.phase == 'Rearing':
            # Clear existing partitions?
            PartitionWeight.query.filter_by(log_id=log.id).delete()

            f_parts = [f'F{i}' for i in range(1, 9)]
            m_parts = [f'M{i}' for i in range(1, 9)]

            sum_bw_f = 0; count_bw_f = 0
            sum_uni_f = 0; count_uni_f = 0
            sum_bw_m = 0; count_bw_m = 0
            sum_uni_m = 0; count_uni_m = 0

            for p in f_parts + m_parts:
                bw = float(request.form.get(f'bw_{p}') or 0)
                uni = float(request.form.get(f'uni_{p}') or 0)

                if bw > 0:
                    pw = PartitionWeight(log_id=log.id, partition_name=p, body_weight=bw, uniformity=uni)
                    db.session.add(pw)

                    if p.startswith('F'):
                        sum_bw_f += bw; count_bw_f += 1
                        if uni > 0: sum_uni_f += uni; count_uni_f += 1
                    else:
                        sum_bw_m += bw; count_bw_m += 1
                        if uni > 0: sum_uni_m += uni; count_uni_m += 1

            if count_bw_f > 0: bw_f_val = sum_bw_f / count_bw_f
            if count_uni_f > 0: uni_f_val = sum_uni_f / count_uni_f
            if count_bw_m > 0: bw_m_val = sum_bw_m / count_bw_m
            if count_uni_m > 0: uni_m_val = sum_uni_m / count_uni_m

        log.body_weight_male = bw_m_val
        log.body_weight_female = bw_f_val
        log.uniformity_male = uni_m_val
        log.uniformity_female = uni_f_val
        
        log.is_weighing_day = 'is_weighing_day' in request.form
        log.bw_male_p1 = float(request.form.get('bw_M1') or 0)
        log.bw_male_p2 = float(request.form.get('bw_M2') or 0)
        log.unif_male_p1 = float(request.form.get('uni_M1') or 0)
        log.unif_male_p2 = float(request.form.get('uni_M2') or 0)
        log.bw_female_p1 = float(request.form.get('bw_F1') or 0)
        log.bw_female_p2 = float(request.form.get('bw_F2') or 0)
        log.bw_female_p3 = float(request.form.get('bw_F3') or 0)
        log.bw_female_p4 = float(request.form.get('bw_F4') or 0)
        log.unif_female_p1 = float(request.form.get('uni_F1') or 0)
        log.unif_female_p2 = float(request.form.get('uni_F2') or 0)
        log.unif_female_p3 = float(request.form.get('uni_F3') or 0)
        log.unif_female_p4 = float(request.form.get('uni_F4') or 0)
        log.standard_bw_male = float(request.form.get('standard_bw_male') or 0)
        log.standard_bw_female = float(request.form.get('standard_bw_female') or 0)

        log.water_reading_1 = int(request.form.get('water_reading_1') or 0)
        log.water_reading_2 = int(request.form.get('water_reading_2') or 0)
        log.water_reading_3 = int(request.form.get('water_reading_3') or 0)
        log.flushing = True if request.form.get('flushing') else False
        
        log.light_on_time = request.form.get('light_on_time')
        log.light_off_time = request.form.get('light_off_time')
        log.feed_cleanup_start = request.form.get('feed_cleanup_start')
        log.feed_cleanup_end = request.form.get('feed_cleanup_end')
        log.clinical_notes = request.form.get('clinical_notes')
        
        # Handle Photo Upload (Optional replace)
        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename != '':
                date_str = log.date.strftime('%y%m%d')
                raw_name = f"{log.flock.batch_id}_{date_str}_{file.filename}"
                filename = secure_filename(raw_name)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                log.photo_path = filepath
        
        # Recalculate Water
        from datetime import timedelta
        yesterday = log.date - timedelta(days=1)
        yesterday_log = DailyLog.query.filter_by(flock_id=log.flock_id, date=yesterday).first()
        
        if yesterday_log:
            r1_today_real = log.water_reading_1 / 100.0
            r1_yesterday_real = yesterday_log.water_reading_1 / 100.0
            log.water_intake_calculated = (r1_today_real - r1_yesterday_real) * 1000.0
        
        db.session.commit()
        flash('Log updated successfully.', 'success')
        return redirect(url_for('view_flock', id=log.flock_id))
    
    feed_codes = FeedCode.query.order_by(FeedCode.code.asc()).all()
    return render_template('daily_log_form.html', log=log, houses=[log.flock.house], feed_codes=feed_codes)

@app.route('/import', methods=['GET', 'POST'])
def import_data():
    if request.method == 'POST':
        if 'files' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        
        files = request.files.getlist('files')
        if not files or files[0].filename == '':
            flash('No selected files', 'danger')
            return redirect(request.url)

        success_count = 0
        errors = []

        for file in files:
            if file and file.filename.endswith('.xlsx'):
                try:
                    process_import(file)
                    success_count += 1
                except Exception as e:
                    errors.append(f"{file.filename}: {str(e)}")
            else:
                if file.filename:
                    errors.append(f"{file.filename}: Invalid type (must be .xlsx)")

        if success_count > 0:
            flash(f'Successfully imported {success_count} files.', 'success')

        if errors:
            flash(f'Errors occurred: {"; ".join(errors)}', 'danger')

        return redirect(url_for('index'))
            
    return render_template('import.html')

def process_import(file):
    import pandas as pd
    
    xls = pd.ExcelFile(file)
    sheets = xls.sheet_names
    
    ignore_sheets = ['DASHBOARD', 'CHART', 'SUMMARY', 'TEMPLATE']
    
    for sheet_name in sheets:
        if sheet_name.upper() in ignore_sheets:
            continue
            
        # Read Metadata (unchanged)
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
                # Handle various formats
                formats = ['%Y-%m-%d', '%d/%m/%y', '%d/%m/%Y', '%m/%d/%Y', '%m/%d/%y']
                for fmt in formats:
                    try:
                        return datetime.strptime(date_val, fmt).date()
                    except ValueError:
                        continue
            return None

        house_name_cell = str(get_val(1, 1)).strip() # B2
        house_name = house_name_cell if house_name_cell and house_name_cell != 'nan' else sheet_name
        
        intake_female = int(get_val(2, 1) or 0) # B3
        intake_male = int(get_val(3, 1) or 0)   # B4
        intake_date_val = get_val(4, 1)         # B5
        
        if not intake_date_val:
            print(f"Skipping sheet {sheet_name}: No Intake Date found.")
            continue
            
        # Find or Create House
        house = House.query.filter_by(name=house_name).first()
        if not house:
            house = House(name=house_name)
            db.session.add(house)
            db.session.commit()
        
        # Find or Create Flock
        intake_date = parse_date(intake_date_val)
        if not intake_date:
            print(f"Skipping sheet {sheet_name}: Invalid Date {intake_date_val}")
            continue
            
        date_str = intake_date.strftime('%y%m%d')
        
        flock = Flock.query.filter_by(house_id=house.id, intake_date=intake_date).first()
        if not flock:
            house_flock_count = Flock.query.filter_by(house_id=house.id).count()
            n = house_flock_count + 1
            batch_id = f"{house.name}_{date_str}_Batch{n}"
            
            flock = Flock(
                house_id=house.id,
                batch_id=batch_id,
                intake_date=intake_date,
                intake_male=intake_male,
                intake_female=intake_female,
                status='Active'
            )
            db.session.add(flock)
            db.session.commit()
            
            initialize_sampling_schedule(flock.id)

        # Cache existing logs for this flock to avoid N+1 queries
        existing_logs_dict = {log.date: log for log in DailyLog.query.filter_by(flock_id=flock.id).all()}

        # Read Data - STARTING ROW 11 (0-index 10)
        df_data = pd.read_excel(xls, sheet_name=sheet_name, header=None, skiprows=10, nrows=490)
        # Phase 1: Standard BW Extraction (Rows 508-571)
        # Week number in Col A (Index 0), Male BW in Col AG (Index 32 - actually let's check), Female BW in Col AH (Index 33)
        # Wait, header=8 means Row 9 is header.
        # "row 508 - 571" in Excel means index 507 to 570 in 0-based index if reading whole file.
        # Since we read from header=8 (row 9), the index in df_data will be (508 - 10) = ~498.
        # But safest is to read these rows explicitly via skiprows/nrows or just scan df_data if it's large enough.

        # Let's read standard BW separately to be robust.
        df_std = pd.read_excel(xls, sheet_name=sheet_name, header=None, skiprows=507, nrows=70) # 508 to ~578
        standard_bw_map = {}

        for _, s_row in df_std.iterrows():
            try:
                # Col A = Week (0)
                week = int(s_row.iloc[0])
                # Col AG = 32 (A=0... Z=25, AA=26... AG=32)
                # Col AH = 33
                std_m = float(s_row.iloc[32]) if pd.notna(s_row.iloc[32]) else 0.0
                std_f = float(s_row.iloc[33]) if pd.notna(s_row.iloc[33]) else 0.0
                standard_bw_map[week] = (std_m, std_f)
            except:
                continue

        # Phase 2: Read Data
        df_data = pd.read_excel(xls, sheet_name=sheet_name, header=8)
        
        # Track rows to skip logic for BW if they are part of a partition block
        partition_rows_indices = set()

        # First Pass: Identify Partition Blocks
        # We look for blocks where multiple consecutive rows have data in BW columns but maybe same date or special pattern?
        # User said: "subsequent value before hitting blank cells is in week X... row 46-49".
        # This implies we scan row by row. If we see BW data:
        # Check if it is "Partition 1". How?
        # If the *previous* row had NO BW data (or was a normal day without weighing?), this is start.
        # Actually, simpler: Any row with BW data is potentially part of a block.
        # User said "first row is the marking date for weighing date".

        # Let's collect data first
        data_rows = []
        for index, row in df_data.iterrows():
            # Date is Column 2 (Index 1)
            date_val = row.iloc[1]
            if pd.isna(date_val):
                continue

            log_date = parse_date(date_val)
            if log_date:
                data_rows.append(row)

        i = 0
        while i < len(data_rows):
            row = data_rows[i]
            if len(row) < 2:
                i+=1
                continue

            # Date Handling
            date_val = row.iloc[1] # Col B
            log_date = parse_date(date_val)

            if not log_date:
                i+=1
                continue

            # Ensure Log Exists - Using cache to avoid N+1 queries
            log = existing_logs_dict.get(log_date)
            if not log:
                log = DailyLog(flock_id=flock.id, date=log_date)
                db.session.add(log)
                existing_logs_dict[log_date] = log
            
            # Helper Helpers
            def get_float(r, idx):
                if idx >= len(r): return 0.0
                val = r.iloc[idx]
                return float(val) if pd.notna(val) and isinstance(val, (int, float)) else 0.0

            def get_int(r, idx):
                if idx >= len(r): return 0
                val = r.iloc[idx]
                return int(val) if pd.notna(val) and isinstance(val, (int, float)) else 0
                
            def get_str(r, idx):
                if idx >= len(r): return None
                val = r.iloc[idx]
                return str(val) if pd.notna(val) else None

            def get_time(r, idx):
                if idx >= len(r): return None
                val = r.iloc[idx]
                if pd.isna(val): return None
                if isinstance(val, str): return val
                return val.strftime('%H:%M') if hasattr(val, 'strftime') else str(val)

            # Standard Data
            log.culls_male = get_int(row, 2)
            log.culls_female = get_int(row, 3)
            log.mortality_male = get_int(row, 4)
            log.mortality_female = get_int(row, 5)

            log.feed_male_gp_bird = get_float(row, 16)
            log.feed_female_gp_bird = get_float(row, 17)

            log.eggs_collected = get_int(row, 24)
            log.cull_eggs_jumbo = get_int(row, 25)
            log.cull_eggs_small = get_int(row, 26)
            log.cull_eggs_abnormal = get_int(row, 27)
            log.cull_eggs_crack = get_int(row, 28)
            log.egg_weight = get_float(row, 29)

            log.water_reading_1 = get_int(row, 43)
            log.water_reading_2 = get_int(row, 44)
            log.water_reading_3 = get_int(row, 45)

            log.light_on_time = get_time(row, 50)
            log.light_off_time = get_time(row, 51)
            log.feed_cleanup_start = get_time(row, 53)
            log.feed_cleanup_end = get_time(row, 54)

            val_rem = row.iloc[56] if len(row) > 56 else None
            log.clinical_notes = str(val_rem) if pd.notna(val_rem) else None

            # --- Partition / Weighing Logic ---
            # Check if this row has BW data
            bw_m = get_float(row, 39)
            bw_f = get_float(row, 41)
            unif_m = get_float(row, 40)
            unif_f = get_float(row, 42)

            has_bw = (bw_m > 0 or bw_f > 0)

            # If we are already in a "consumed" row (detected previously as part of a block), skip BW processing?
            # Actually, better approach:
            # If has_bw is True, check if this is the START of a block.
            # A block starts if:
            # 1. It has BW data.
            # 2. It is NOT identified as a continuation of a previous block.
            # Since we iterate sequentially, we can just consume ahead.

            if has_bw:
                # Assume this is P1 (Partition 1)
                log.is_weighing_day = True

                # Load Standard BW
                # Calculate Week
                days_diff = (log.date - flock.intake_date).days
                week_num = (days_diff // 7) + 1
                if week_num in standard_bw_map:
                    log.standard_bw_male = standard_bw_map[week_num][0]
                    log.standard_bw_female = standard_bw_map[week_num][1]

                # Male P1
                log.bw_male_p1 = bw_m
                log.unif_male_p1 = unif_m
                # Female P1
                log.bw_female_p1 = bw_f
                log.unif_female_p1 = unif_f

                # Now peek ahead for P2, P3, P4
                # We expect up to 3 more rows to have BW data (total 4 for female, 2 for male)
                # User: "row 46 is partition 1 until row 49 is partition 4"
                # So next row is P2, next P3, next P4.

                # Check next row (i+1) -> P2
                if i + 1 < len(data_rows):
                    row2 = data_rows[i+1]
                    bw_m2 = get_float(row2, 39)
                    bw_f2 = get_float(row2, 41)
                    if bw_m2 > 0 or bw_f2 > 0:
                        log.bw_male_p2 = bw_m2
                        log.unif_male_p2 = get_float(row2, 40)

                        log.bw_female_p2 = bw_f2
                        log.unif_female_p2 = get_float(row2, 42)

                        # Clear BW from that daily log to avoid duplicates?
                        # We must update that day's log (which will be processed in next loop iteration)
                        # to NOT treat it as a weighing day.
                        # But wait, the next loop iteration will process `row2`.
                        # We need to tell it "Skip BW for this row".
                        # Let's modify the row in memory? Or set a flag?
                        # Using `partition_rows_indices`
                        partition_rows_indices.add(i+1)

                # Check next row (i+2) -> P3 (Female only usually, but let's see)
                if i + 2 < len(data_rows):
                    row3 = data_rows[i+2]
                    bw_f3 = get_float(row3, 41)
                    if bw_f3 > 0:
                        log.bw_female_p3 = bw_f3
                        log.unif_female_p3 = get_float(row3, 42)
                        partition_rows_indices.add(i+2)

                # Check next row (i+3) -> P4
                if i + 3 < len(data_rows):
                    row4 = data_rows[i+3]
                    bw_f4 = get_float(row4, 41)
                    if bw_f4 > 0:
                        log.bw_female_p4 = bw_f4
                        log.unif_female_p4 = get_float(row4, 42)
                        partition_rows_indices.add(i+3)

            # If this row was marked as a "Partition continuation row" (P2/P3/P4),
            # ensure we DON'T overwrite the main BW fields with these partition chunks
            # effectively treating them as 0 for the "Average" (which we will calculate later or ignore)
            if i in partition_rows_indices:
                log.body_weight_male = 0
                log.body_weight_female = 0
                log.uniformity_male = 0
                log.uniformity_female = 0
                log.is_weighing_day = False # Ensure it doesn't trigger again
            else:
                # If it's a normal weighing day (P1), we keep the values in `bw_male_p1` etc.
                # Do we also keep `body_weight_male`?
                # User wants "Average" to be calculated.
                # If we just imported P1..P4, let's calculate the average NOW and store it in body_weight_male/female.
                if has_bw:
                    # Calculate Average Male
                    m_count = 0
                    m_sum = 0
                    if log.bw_male_p1 > 0: m_sum += log.bw_male_p1; m_count += 1
                    if log.bw_male_p2 > 0: m_sum += log.bw_male_p2; m_count += 1
                    log.body_weight_male = (m_sum / m_count) if m_count > 0 else 0

                    # Calculate Average Female
                    f_count = 0
                    f_sum = 0
                    if log.bw_female_p1 > 0: f_sum += log.bw_female_p1; f_count += 1
                    if log.bw_female_p2 > 0: f_sum += log.bw_female_p2; f_count += 1
                    if log.bw_female_p3 > 0: f_sum += log.bw_female_p3; f_count += 1
                    if log.bw_female_p4 > 0: f_sum += log.bw_female_p4; f_count += 1
                    log.body_weight_female = (f_sum / f_count) if f_count > 0 else 0

                    # Uniformity Average? (Simple average of %s)
                    m_u_sum = 0
                    if log.unif_male_p1 > 0: m_u_sum += log.unif_male_p1
                    if log.unif_male_p2 > 0: m_u_sum += log.unif_male_p2
                    log.uniformity_male = (m_u_sum / m_count) if m_count > 0 else 0

                    f_u_sum = 0
                    if log.unif_female_p1 > 0: f_u_sum += log.unif_female_p1
                    if log.unif_female_p2 > 0: f_u_sum += log.unif_female_p2
                    if log.unif_female_p3 > 0: f_u_sum += log.unif_female_p3
                    if log.unif_female_p4 > 0: f_u_sum += log.unif_female_p4
                    log.uniformity_female = (f_u_sum / f_count) if f_count > 0 else 0

            i += 1

        db.session.commit()
        
        # Recalculate Water - Fetch once to avoid reloads after commit
        all_logs = DailyLog.query.filter_by(flock_id=flock.id).order_by(DailyLog.date).all()
        for i, log in enumerate(all_logs):
            if i > 0:
                prev_log = all_logs[i-1]
                if prev_log.water_reading_1 and log.water_reading_1:
                    r1_today = log.water_reading_1 / 100.0
                    r1_prev = prev_log.water_reading_1 / 100.0
                    log.water_intake_calculated = (r1_today - r1_prev) * 1000.0
                    db.session.add(log)
        db.session.commit()

        verify_import_data(flock, logs=all_logs)

def verify_import_data(flock, logs=None):
    # Compare ImportedWeeklyBenchmark with DailyLog Aggregates
    weekly_records = ImportedWeeklyBenchmark.query.filter_by(flock_id=flock.id).order_by(ImportedWeeklyBenchmark.week).all()
    if logs is None:
        logs = DailyLog.query.filter_by(flock_id=flock.id).all()

    warnings = []

    # Aggregate Logs by Week
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
            # Check Mortality Female
            if abs(calc['mort_f'] - wd.mortality_female) > 1: # Tolerance of 1
                warnings.append(f"Week {wd.week}: Calc Mort F ({calc['mort_f']}) != Imported ({wd.mortality_female})")

            # Check Eggs
            if abs(calc['eggs'] - wd.eggs_collected) > 5: # Tolerance
                warnings.append(f"Week {wd.week}: Calc Eggs ({calc['eggs']}) != Imported ({wd.eggs_collected})")

    if warnings:
        flash(f"Import Verification Warnings: {'; '.join(warnings[:3])}...", 'warning')
