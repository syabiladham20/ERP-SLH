from flask import render_template, request, redirect, flash, url_for, session, jsonify
from flask_login import login_required, current_user
from app.database import db
from app.models.models import *
from sqlalchemy.orm import joinedload
from sqlalchemy import func, or_, and_
import os
from datetime import datetime, date, timedelta
import calendar

def register_hatchery_routes(app):

    from app.constants import (
        FARM_HATCHERY_ADMIN_MGMT_DEPTS, FARM_HATCHERY_ADMIN_DEPTS,
    )
    from app.utils import safe_commit, log_user_activity, dept_required, natural_sort_key
    from app.services.data_service import calculate_male_ratio, process_hatchability_import

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
