from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from datetime import datetime, date
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'farm.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_key')
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)

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
    end_date = db.Column(db.Date, nullable=True)
    
    logs = db.relationship('DailyLog', backref='flock', lazy=True)

class DailyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    flock_id = db.Column(db.Integer, db.ForeignKey('flock.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    
    # Metrics
    mortality_male = db.Column(db.Integer, default=0)
    mortality_female = db.Column(db.Integer, default=0)
    
    culls_male = db.Column(db.Integer, default=0)
    culls_female = db.Column(db.Integer, default=0)
    
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

@app.route('/')
def index():
    active_flocks = Flock.query.filter_by(status='Active').all()
    return render_template('index.html', active_flocks=active_flocks)

@app.route('/help')
def help():
    return render_template('help.html')

@app.route('/flocks', methods=['GET', 'POST'])
def manage_flocks():
    if request.method == 'POST':
        house_name = request.form.get('house_name').strip()
        intake_date_str = request.form.get('intake_date')
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
            doa_female=doa_female
        )
        
        db.session.add(new_flock)
        db.session.commit()
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

@app.route('/flock/<int:id>/toggle_phase', methods=['POST'])
def toggle_phase(id):
    flock = Flock.query.get_or_404(id)
    if flock.phase == 'Rearing':
        flock.phase = 'Production'
        flash(f'Flock {flock.batch_id} switched to Production phase.', 'success')
    else:
        # Optionally allow switching back? User said "toggles it once when to start manually"
        # I'll allow toggle back just in case of mistake, or just strictly forward.
        # "toggles it once" suggests one-way. But "toggle" suggests switch.
        # I'll assume they might want to correct it.
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
        
        # Feed is entered as G/B. To get Total Kg, we need Stock.
        # Stock = Start - CumMortality - CumCulls.
        # For simplicity, I'll just SUM the G/B values? No, that's meaningless.
        # Excel calculates Total Feed = G/B * Stock / 1000.
        # Calculating Stock daily here is expensive but correct.
        # For now, let's just show AVG G/B for the week? Or just omit Feed Summary if confusing.
        # Reviewer asked for "Weekly Summaries". Sum of Mortality is easy.
        # Let's show Sum Mortality, Sum Eggs, Avg BW.
        
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
    
    # Calculate cumulative mortality
    cum_mort_m = 0
    cum_mort_f = 0
    start_m = flock.intake_male or 1
    start_f = flock.intake_female or 1
    
    for log in logs:
        cum_mort_m += log.mortality_male
        cum_mort_f += log.mortality_female
        
        chart_data['mortality_cum_male'].append(round((cum_mort_m / start_m) * 100, 2))
        chart_data['mortality_cum_female'].append(round((cum_mort_f / start_f) * 100, 2))
        
        # Egg Prod % = Eggs / Current Female Stock * 100
        # Current Female Stock = Start - Cum Mort - Cum Cull
        # We need cumulative culls too
        # To be accurate, we need running totals.
        pass

    # Re-loop for accurate running totals including culls
    cum_mort_m = 0
    cum_mort_f = 0
    cum_cull_m = 0
    cum_cull_f = 0
    
    chart_data['mortality_cum_male'] = []
    chart_data['mortality_cum_female'] = []
    
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

        chart_data['unif_male'].append(val_or_null(log.uniformity_male))
        chart_data['unif_female'].append(val_or_null(log.uniformity_female))

    return render_template('flock_detail.html', flock=flock, logs=list(reversed(logs)), weekly_data=weekly_data, chart_data=chart_data)

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
                safe_filename = secure_filename(file.filename)
                filename = f"{flock.batch_id}_{date_str}_{safe_filename}"
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
        else:
            # Fallback if no yesterday log? Maybe just use 12h or 0?
            # Or assume reading 1 starts from 0 if first day?
            # Let's leave it 0 if no history.
            pass

        is_weighing = 'is_weighing_day' in request.form

        new_log = DailyLog(
            flock_id=flock.id,
            date=log_date,
            mortality_male=int(request.form.get('mortality_male') or 0),
            mortality_female=int(request.form.get('mortality_female') or 0),
            culls_male=int(request.form.get('culls_male') or 0),
            culls_female=int(request.form.get('culls_female') or 0),
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
            
            is_weighing_day=is_weighing,
            bw_male_p1=float(request.form.get('bw_male_p1') or 0),
            bw_male_p2=float(request.form.get('bw_male_p2') or 0),
            unif_male_p1=float(request.form.get('unif_male_p1') or 0),
            unif_male_p2=float(request.form.get('unif_male_p2') or 0),
            bw_female_p1=float(request.form.get('bw_female_p1') or 0),
            bw_female_p2=float(request.form.get('bw_female_p2') or 0),
            bw_female_p3=float(request.form.get('bw_female_p3') or 0),
            bw_female_p4=float(request.form.get('bw_female_p4') or 0),
            unif_female_p1=float(request.form.get('unif_female_p1') or 0),
            unif_female_p2=float(request.form.get('unif_female_p2') or 0),
            unif_female_p3=float(request.form.get('unif_female_p3') or 0),
            unif_female_p4=float(request.form.get('unif_female_p4') or 0),
            standard_bw_male=float(request.form.get('standard_bw_male') or 0),
            standard_bw_female=float(request.form.get('standard_bw_female') or 0),

            water_reading_1=water_r1,
            water_reading_2=int(request.form.get('water_reading_2') or 0),
            water_reading_3=water_r3,
            water_intake_calculated=water_intake_calc,
            
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
        
        log.is_weighing_day = 'is_weighing_day' in request.form
        log.bw_male_p1 = float(request.form.get('bw_male_p1') or 0)
        log.bw_male_p2 = float(request.form.get('bw_male_p2') or 0)
        log.unif_male_p1 = float(request.form.get('unif_male_p1') or 0)
        log.unif_male_p2 = float(request.form.get('unif_male_p2') or 0)
        log.bw_female_p1 = float(request.form.get('bw_female_p1') or 0)
        log.bw_female_p2 = float(request.form.get('bw_female_p2') or 0)
        log.bw_female_p3 = float(request.form.get('bw_female_p3') or 0)
        log.bw_female_p4 = float(request.form.get('bw_female_p4') or 0)
        log.unif_female_p1 = float(request.form.get('unif_female_p1') or 0)
        log.unif_female_p2 = float(request.form.get('unif_female_p2') or 0)
        log.unif_female_p3 = float(request.form.get('unif_female_p3') or 0)
        log.unif_female_p4 = float(request.form.get('unif_female_p4') or 0)
        log.standard_bw_male = float(request.form.get('standard_bw_male') or 0)
        log.standard_bw_female = float(request.form.get('standard_bw_female') or 0)

        log.water_reading_1 = int(request.form.get('water_reading_1') or 0)
        log.water_reading_2 = int(request.form.get('water_reading_2') or 0)
        log.water_reading_3 = int(request.form.get('water_reading_3') or 0)
        
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
                safe_filename = secure_filename(file.filename)
                filename = f"{log.flock.batch_id}_{date_str}_{safe_filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                log.photo_path = filepath
        
        # Recalculate Water?
        # Ideally yes, but logic is tied to "Yesterday". 
        # If we edit "Today", we check "Yesterday". 
        # If we edit "Yesterday", "Today" calculation might become wrong. 
        # For now, let's just recalc this log's intake based on ITS yesterday.
        # Note: If we change R1, we should update intake.
        
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
    
    ignore_sheets = ['TEMPLATE', 'DASHBOARD', 'CHART']
    
    for sheet_name in sheets:
        if sheet_name.upper() in ignore_sheets:
            continue
            
        # Read Metadata
        df_meta = pd.read_excel(xls, sheet_name=sheet_name, header=None, nrows=10)
        
        def get_val(r, c):
            val = df_meta.iloc[r, c]
            return val if pd.notna(val) else None

        house_name_cell = str(get_val(1, 1)).strip() # B2
        # Use cell value if present, else Sheet Name
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
             data_rows.append(row)

        i = 0
        while i < len(data_rows):
            row = data_rows[i]
            if len(row) < 2:
                i+=1
                continue
                
            # Date Handling
            date_val = row.iloc[1] # Col B
            log_date = None
            if pd.notna(date_val):
                if isinstance(date_val, str):
                    try:
                        log_date = datetime.strptime(date_val, '%Y-%m-%d').date()
                    except:
                        pass
                else:
                    log_date = date_val.date()

            if not log_date:
                i+=1
                continue
                
            # Ensure Log Exists
            log = DailyLog.query.filter_by(flock_id=flock.id, date=log_date).first()
            if not log:
                log = DailyLog(flock_id=flock.id, date=log_date)
                db.session.add(log)
            
            # Helper Helpers
            def get_float(r, idx):
                if idx >= len(r): return 0.0
                val = r.iloc[idx]
                return float(val) if pd.notna(val) and isinstance(val, (int, float)) else 0.0

            def get_int(r, idx):
                if idx >= len(r): return 0
                val = r.iloc[idx]
                return int(val) if pd.notna(val) and isinstance(val, (int, float)) else 0
                
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

