from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from datetime import datetime, date
import os

app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'farm.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'dev_key'  # Change for production
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)

from flask import send_from_directory

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

db = SQLAlchemy(app)

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
    
    logs = db.relationship('DailyLog', backref='flock', lazy=True)

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

    @property
    def age_week_day(self):
        delta = (self.date - self.flock.intake_date).days
        if delta < 1:
            return "0.0"
        weeks = (delta - 1) // 7
        days = (delta - 1) % 7 + 1
        return f"{weeks}.{days}"

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
    flock = db.relationship('Flock', backref='sampling_events')
    age_week = db.Column(db.Integer, nullable=False)
    test_type = db.Column(db.String(50), nullable=False) # 'Serology', 'Salmonella', 'Serology & Salmonella'
    status = db.Column(db.String(20), default='Pending') # 'Pending', 'Completed'
    result_file = db.Column(db.String(200), nullable=True) # Path to PDF
    upload_date = db.Column(db.Date, nullable=True)
    remarks = db.Column(db.String(255), nullable=True)

    @property
    def scheduled_date(self):
        from datetime import timedelta
        # Week 1 starts on Day 0 (Intake Date).
        # Week N starts on Intake + (N-1)*7 days.
        days_offset = (self.age_week - 1) * 7
        return self.flock.intake_date + timedelta(days=days_offset)

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

    return render_template('index.html', active_flocks=active_flocks)

@app.route('/flock/<int:id>/delete', methods=['POST'])
def delete_flock(id):
    flock = Flock.query.get_or_404(id)
    # Cascade delete logs? SQLAlchemy relationship usually handles if configured,
    # but here we didn't set cascade="all, delete". Manual delete safest.
    DailyLog.query.filter_by(flock_id=id).delete()
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
        flash(f'Flock {flock.batch_id} switched to Production phase.', 'success')
    else:
        flock.phase = 'Rearing'
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
        'bw_male': [],
        'bw_female': []
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
        
        chart_data['bw_male'].append(log.body_weight_male)
        chart_data['bw_female'].append(log.body_weight_female)

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
    for k in kpis:
        k['diff'] = k['value'] - k['prev']
        k['status'] = 'neutral'

        if k['std'] is not None and k['value'] > 0:
            # Anomaly Detection Logic
            if k['reverse_bad']: # Higher than std is bad
                if k['value'] > k['std'] * 1.1: # 10% tolerance?
                    k['status'] = 'danger'
                elif k['value'] > k['std']:
                    k['status'] = 'warning'
            else: # Lower than std is bad
                if k['value'] < k['std'] * 0.9:
                    k['status'] = 'danger'
                elif k['value'] < k['std']:
                    k['status'] = 'warning'

    return render_template('flock_kpi.html', flock=flock, kpis=kpis, target_date=target_date, age_week=age_week, age_days=age_days)

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
            
            feed_male_gp_bird=float(request.form.get('feed_male_gp_bird') or 0),
            feed_female_gp_bird=float(request.form.get('feed_female_gp_bird') or 0),
            
            eggs_collected=int(request.form.get('eggs_collected') or 0),
            cull_eggs_jumbo=int(request.form.get('cull_eggs_jumbo') or 0),
            cull_eggs_small=int(request.form.get('cull_eggs_small') or 0),
            cull_eggs_abnormal=int(request.form.get('cull_eggs_abnormal') or 0),
            cull_eggs_crack=int(request.form.get('cull_eggs_crack') or 0),
            egg_weight=float(request.form.get('egg_weight') or 0),
            
            body_weight_male=float(request.form.get('body_weight_male') or 0),
            body_weight_female=float(request.form.get('body_weight_female') or 0),
            uniformity_male=float(request.form.get('uniformity_male') or 0),
            uniformity_female=float(request.form.get('uniformity_female') or 0),
            
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
        flash('Daily Log submitted successfully!', 'success')
        return redirect(url_for('index'))
        
    # GET: Only show houses with Active flocks
    active_flocks = Flock.query.filter_by(status='Active').all()
    active_houses = [f.house for f in active_flocks]
    return render_template('daily_log_form.html', houses=active_houses)

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
        log.feed_male_gp_bird = float(request.form.get('feed_male_gp_bird') or 0)
        log.feed_female_gp_bird = float(request.form.get('feed_female_gp_bird') or 0)
        
        log.eggs_collected = int(request.form.get('eggs_collected') or 0)
        log.cull_eggs_jumbo = int(request.form.get('cull_eggs_jumbo') or 0)
        log.cull_eggs_small = int(request.form.get('cull_eggs_small') or 0)
        log.cull_eggs_abnormal = int(request.form.get('cull_eggs_abnormal') or 0)
        log.cull_eggs_crack = int(request.form.get('cull_eggs_crack') or 0)
        log.egg_weight = float(request.form.get('egg_weight') or 0)
        
        log.body_weight_male = float(request.form.get('body_weight_male') or 0)
        log.body_weight_female = float(request.form.get('body_weight_female') or 0)
        log.uniformity_male = float(request.form.get('uniformity_male') or 0)
        log.uniformity_female = float(request.form.get('uniformity_female') or 0)
        
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
    
    return render_template('daily_log_form.html', log=log, houses=[log.flock.house])

@app.route('/import', methods=['GET', 'POST'])
def import_data():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
        
        if file and file.filename.endswith('.xlsx'):
            try:
                process_import(file)
                flash('Data imported successfully!', 'success')
                return redirect(url_for('index'))
            except Exception as e:
                flash(f'Error importing file: {str(e)}', 'danger')
                return redirect(request.url)
        else:
            flash('Invalid file type. Please upload an Excel (.xlsx) file.', 'danger')
            return redirect(request.url)
            
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
        if isinstance(intake_date_val, str):
            try:
                intake_date = datetime.strptime(intake_date_val, '%Y-%m-%d').date()
            except:
                print(f"Skipping sheet {sheet_name}: Invalid Date {intake_date_val}")
                continue
        else:
            intake_date = intake_date_val.date()
            
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

        # Read Data - STARTING ROW 11 (0-index 10)
        df_data = pd.read_excel(xls, sheet_name=sheet_name, header=None, skiprows=10, nrows=490)
        
        for index, row in df_data.iterrows():
            # Date is Column 2 (Index 1)
            date_val = row.iloc[1]
            if pd.isna(date_val):
                continue
                
            if isinstance(date_val, str):
                try:
                    log_date = datetime.strptime(date_val, '%Y-%m-%d').date()
                except:
                    continue
            elif hasattr(date_val, 'date'):
                log_date = date_val.date()
            else:
                continue
                
            log = DailyLog.query.filter_by(flock_id=flock.id, date=log_date).first()
            if not log:
                log = DailyLog(flock_id=flock.id, date=log_date)
                db.session.add(log)
            
            def get_float(idx):
                if idx >= len(row): return 0.0
                val = row.iloc[idx]
                return float(val) if pd.notna(val) and isinstance(val, (int, float)) else 0.0
                
            def get_int(idx):
                if idx >= len(row): return 0
                val = row.iloc[idx]
                return int(val) if pd.notna(val) and isinstance(val, (int, float)) else 0
                
            def get_str(idx):
                if idx >= len(row): return None
                val = row.iloc[idx]
                return str(val) if pd.notna(val) else None

            def get_time(idx):
                if idx >= len(row): return None
                val = row.iloc[idx]
                if pd.isna(val): return None
                if isinstance(val, str): return val
                return val.strftime('%H:%M') if hasattr(val, 'strftime') else str(val)

            # Updated Mapping
            log.culls_male = get_int(2)       # C
            log.culls_female = get_int(3)     # D
            log.mortality_male = get_int(4)   # E
            log.mortality_female = get_int(5) # F

            log.feed_program = get_str(15)    # P
            log.feed_male_gp_bird = get_float(16)   # Q
            log.feed_female_gp_bird = get_float(17) # R

            log.eggs_collected = get_int(24)      # Y
            log.cull_eggs_jumbo = get_int(25)     # Z
            log.cull_eggs_small = get_int(26)     # AA
            log.cull_eggs_abnormal = get_int(27)  # AB
            log.cull_eggs_crack = get_int(28)     # AC
            log.egg_weight = get_float(29)        # AD

            log.body_weight_male = get_float(39)  # AN
            log.uniformity_male = get_float(40)   # AO
            log.body_weight_female = get_float(41)# AP
            log.uniformity_female = get_float(42) # AQ
            
            log.water_reading_1 = get_int(43)     # AR
            log.water_reading_2 = get_int(44)     # AS
            log.water_reading_3 = get_int(45)     # AT
            
            log.light_on_time = get_time(50)      # AY
            log.light_off_time = get_time(51)     # AZ
            log.feed_cleanup_start = get_time(53) # BB
            log.feed_cleanup_end = get_time(54)   # BC
            
            log.clinical_notes = get_str(56)      # BE
            
            # --- Extract Daily Standards ---
            # Standard Male Feed (22), Female Feed (23) - W, X
            std_feed_m = get_float(22)
            std_feed_f = get_float(23)

            delta = (log_date - flock.intake_date).days
            week_num = (delta // 7) + 1

            if week_num > 0 and (std_feed_m > 0 or std_feed_f > 0):
                std = Standard.query.filter_by(week=week_num).first()
                if not std:
                    std = Standard(week=week_num)
                    db.session.add(std)
                if std_feed_m > 0: std.std_feed_male = std_feed_m
                if std_feed_f > 0: std.std_feed_female = std_feed_f

        db.session.commit()
        
        # --- WEEKLY DATA IMPORT (Benchmark) ---
        # Data Start Row 508 (Index 507)
        df_weekly = pd.read_excel(xls, sheet_name=sheet_name, header=None, skiprows=507, nrows=70)

        for index, row in df_weekly.iterrows():
            def get_w_float(idx):
                if idx >= len(row): return 0.0
                val = row.iloc[idx]
                return float(val) if pd.notna(val) and isinstance(val, (int, float)) else 0.0

            def get_w_int(idx):
                if idx >= len(row): return 0
                val = row.iloc[idx]
                return int(val) if pd.notna(val) and isinstance(val, (int, float)) else 0

            week_val = row.iloc[0]
            if pd.isna(week_val): continue
            try:
                week_num = int(week_val)
            except:
                continue

            # Use ImportedWeeklyBenchmark
            wd = ImportedWeeklyBenchmark.query.filter_by(flock_id=flock.id, week=week_num).first()
            if not wd:
                wd = ImportedWeeklyBenchmark(flock_id=flock.id, week=week_num)
                db.session.add(wd)

            wd.mortality_male = get_w_int(2)
            wd.culls_male = get_w_int(3)
            wd.mortality_female = get_w_int(4)

            wd.eggs_collected = get_w_int(18)

            wd.bw_male = get_w_float(28)
            wd.bw_female = get_w_float(30)

            # Extract Weekly Standards
            std_mort_pct = get_w_float(14)
            std_bw_m = get_w_float(32)
            std_bw_f = get_w_float(33)

            std = Standard.query.filter_by(week=week_num).first()
            if not std:
                std = Standard(week=week_num)
                db.session.add(std)

            if std_mort_pct > 0:
                std.std_mortality_female = std_mort_pct * 100
                std.std_mortality_male = std_mort_pct * 100

            if std_bw_m > 0: std.std_bw_male = std_bw_m
            if std_bw_f > 0: std.std_bw_female = std_bw_f

        db.session.commit()
        
        # Recalculate Water
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

        verify_import_data(flock)

def verify_import_data(flock):
    # Compare ImportedWeeklyBenchmark with DailyLog Aggregates
    weekly_records = ImportedWeeklyBenchmark.query.filter_by(flock_id=flock.id).order_by(ImportedWeeklyBenchmark.week).all()
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
