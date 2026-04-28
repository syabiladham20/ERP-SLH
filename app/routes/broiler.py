from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models.models import BroilerFlock, BroilerDailyLog
from app.database import db
from metrics import calculate_broiler_metrics
from datetime import datetime

broiler_bp = Blueprint('broiler', __name__, url_prefix='/broiler')

@broiler_bp.route('/dashboard')
def dashboard():
    flocks = BroilerFlock.query.filter_by(is_active=True).all()
    return render_template('broiler/broiler_dashboard.html', flocks=flocks)

@broiler_bp.route('/new_flock', methods=['GET', 'POST'])
def new_flock():
    if request.method == 'POST':
        farm_name = request.form.get('farm_name')
        house_name = request.form.get('house_name')
        source = request.form.get('source')
        breed = request.form.get('breed')
        intake_birds = int(request.form.get('intake_birds', 0))
        intake_date_str = request.form.get('intake_date')
        arrival_weight_g = float(request.form.get('arrival_weight_g', 0.0))

        intake_date = datetime.strptime(intake_date_str, '%Y-%m-%d').date() if intake_date_str else datetime.utcnow().date()

        flock = BroilerFlock(
            farm_name=farm_name,
            house_name=house_name,
            source=source,
            breed=breed,
            intake_birds=intake_birds,
            intake_date=intake_date,
            arrival_weight_g=arrival_weight_g
        )
        db.session.add(flock)
        db.session.commit()
        flash('Broiler flock created successfully.', 'success')
        return redirect(url_for('broiler.dashboard'))

    return render_template('broiler/broiler_new_flock.html')

@broiler_bp.route('/daily_entry/<int:flock_id>', methods=['GET', 'POST'])
def daily_entry(flock_id):
    flock = BroilerFlock.query.get_or_404(flock_id)

    if request.method == 'POST':
        date_str = request.form.get('date')
        death_count = int(request.form.get('death_count', 0))
        feed_receive = request.form.get('feed_receive')
        feed_type = request.form.get('feed_type')
        feed_daily_use_kg = float(request.form.get('feed_daily_use_kg', 0.0))
        body_weight_g = float(request.form.get('body_weight_g', 0.0))
        medication_vaccine = request.form.get('medication_vaccine')
        remarks = request.form.get('remarks')

        log_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date()

        # Calculate day_number
        day_number = (log_date - flock.intake_date).days + 1

        log = BroilerDailyLog(
            flock_id=flock.id,
            date=log_date,
            day_number=day_number,
            death_count=death_count,
            feed_receive=feed_receive,
            feed_type=feed_type,
            feed_daily_use_kg=feed_daily_use_kg,
            body_weight_g=body_weight_g,
            medication_vaccine=medication_vaccine,
            remarks=remarks
        )
        db.session.add(log)
        db.session.commit()
        flash('Daily log added successfully.', 'success')
        return redirect(url_for('broiler.daily_entry', flock_id=flock.id))

    # Fetch calculated metrics for display
    metrics = calculate_broiler_metrics(flock.id)

    return render_template('broiler/broiler_daily_entry.html', flock=flock, metrics=metrics)
