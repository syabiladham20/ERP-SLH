from flask import render_template, request, redirect, flash, url_for, session, jsonify
from flask_login import login_required, current_user
from app.database import db
from app.models.models import *
from sqlalchemy.orm import joinedload
from sqlalchemy import func, or_, and_
import os
from datetime import datetime, date, timedelta
import calendar
from werkzeug.utils import secure_filename
import pandas as pd
import re
import math
import json
import pytz

def register_health_routes(app):

    from app.constants import (
        EMPTY_NOTE_VALUES,
    )
    from app.utils import safe_commit, send_push_alert, dept_required, natural_sort_key, round_to_whole
    from app.services.data_service import get_flock_stock_history, get_flock_stock_history_bulk, calculate_grading_stats
    from app.services.seed_service import initialize_vaccine_schedule

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

        target_flock_ids = [f.id for f in target_flocks]
        all_medications = Medication.query.filter(Medication.flock_id.in_(target_flock_ids)).order_by(Medication.start_date.desc()).all()

        medications_by_flock = {f_id: [] for f_id in target_flock_ids}
        for med in all_medications:
            medications_by_flock[med.flock_id].append(med)

        for f in target_flocks:
            flock_tasks[f] = {'medications': medications_by_flock[f.id]}

        medication_inventory = InventoryItem.query.filter_by(type='Medication').order_by(InventoryItem.name).all()

        return render_template('health_log_medication.html',
            active_flocks=active_flocks,
            selected_flock_id=int(selected_flock_id) if selected_flock_id else None,
            edit_flock_id=edit_flock_id,
            flock_tasks=flock_tasks,
            medication_inventory=medication_inventory,
            today=today
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

        target_flock_ids = [f.id for f in target_flocks]
        all_samplings = SamplingEvent.query.filter(SamplingEvent.flock_id.in_(target_flock_ids)).order_by(SamplingEvent.age_week).all()

        samplings_by_flock = {f_id: [] for f_id in target_flock_ids}
        for s in all_samplings:
            samplings_by_flock[s.flock_id].append(s)

        for f in target_flocks:
            flock_tasks[f] = {'sampling': samplings_by_flock[f.id]}

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

    @app.route('/health_log')
    def health_log():
        return redirect(url_for('health_log_vaccines'))

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

    @app.route('/flock/<int:id>/sampling')
    @login_required
    @dept_required('Farm')
    def flock_sampling(id):
        flock = Flock.query.options(joinedload(Flock.house)).filter_by(id=id).first_or_404()
        events = SamplingEvent.query.filter_by(flock_id=id).order_by(SamplingEvent.age_week.asc()).all()
        return render_template('flock_sampling.html', flock=flock, events=events)

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
