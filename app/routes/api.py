from app.handlers import APP_VERSION
gemini_engine_instance = None
from metrics import enrich_flock_data, calculate_metrics, aggregate_monthly_metrics, aggregate_weekly_metrics, METRICS_REGISTRY, calculate_bio_week
from analytics import analyze_health_events, calculate_feed_cleanup_duration
from flask import render_template, request, redirect, flash, url_for, session, jsonify, Response
from flask_login import login_required, current_user
from app.database import db
from app.models.models import *
from sqlalchemy.orm import joinedload
from sqlalchemy import func, or_, and_
import os
from datetime import datetime, date, timedelta
import json
import requests
from pywebpush import webpush, WebPushException
import base64
from werkzeug.utils import secure_filename

def register_api_routes(app):

    from app.constants import (
        EMPTY_NOTE_VALUES, ADMIN_FARM_MGMT_ROLES, ALLOWED_EXPORT_ROLES,
    )
    from app.utils import safe_commit, send_push_alert, log_user_activity, dept_required, round_to_whole, get_gemini_response, get_dashboard_url
    from app.services.data_service import generate_spreadsheet_data, recalculate_flock_inventory

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

        flock = Flock.query.get_or_404(flock_id)

        # Fetch ALL logs up to the end_date to ensure cumulative math and stocks calculate correctly from Intake
        logs = DailyLog.query.filter(
            DailyLog.flock_id == flock_id,
            DailyLog.date <= end_date
        ).order_by(DailyLog.date.asc()).all()

        # Fetch Standards
        all_standards = Standard.query.all()
        std_map_by_week = {getattr(s, 'week'): s for s in all_standards if hasattr(s, 'week')}

        gs = GlobalStandard.query.first()
        std_mort = gs.std_mortality_daily if gs and gs.std_mortality_daily is not None else 0.05
        enriched = enrich_flock_data(flock, logs, all_standards=all_standards)

        cum_mort_m_pct = 0
        cum_mort_f_pct = 0
        if enriched:
            # Get phase-aware cumulative mortality from the last calculated day
            cum_mort_m_pct = enriched[-1].get('mortality_cum_male_pct', 0)
            cum_mort_f_pct = enriched[-1].get('mortality_cum_female_pct', 0)

        # Attach Standards
        for d in enriched:
            d['std_mortality'] = std_mort

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
                'std_mortality': entry.get('std_mortality', 0.05),
                'hatching_eggs': entry.get('hatch_eggs', 0),
                'hatching_egg_pct': entry.get('hatch_egg_pct'),
                'std_hatching_pct': entry.get('std_hatching_egg_pct'),
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
            week_num = w.get('week', 0)
            w_log = w.get('log')
            w_item = {
                'week': week_num,
                'bw_male': w.get('body_weight_male', 0.0) or None,
                'bw_female': w.get('body_weight_female', 0.0) or None,
                'uniformity_male': w.get('uniformity_male', 0.0) or None,
                'uniformity_female': w.get('uniformity_female', 0.0) or None,
                'std_bw_male': None,
                'std_bw_female': None,
                'selection_done': any(e['log'].selection_done for e in enriched if e.get('week') == week_num),
                'spiking': any(e['log'].spiking for e in enriched if e.get('week') == week_num)
            }
            # Add std using map
            std_w = std_map_by_week.get(week_num)
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
        total_feed_kg = end_day_log.get('feed_total_kg', 0.0)

        # Get proper standard egg weight for the current week
        std_obj = std_map_by_week.get(end_day_log.get('week', 0))
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

        feed_cleanup_hours = end_day_log.get('feed_cleanup_hours') or 0.0

        notes_str = ", ".join(notes) if notes else "None"
        remarks_str = log.remarks if log.remarks else "None"

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
            'feed_program': log.feed_program or 'N/A',
            'total_feed_kg': round(total_feed_kg, 2),
            'medication': meds_str,
            'vaccination': vaccines_str,
            'notes': notes_str,
            'remarks': remarks_str,
            'trend': trend_data,
            'water_trend': water_trend_data,
            'weekly_trend': weekly_trend
        }

        return jsonify(report_info)

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

    @app.route('/api/metrics')
    def get_metrics_list():
        return json.dumps(METRICS_REGISTRY)

    @app.route('/api/latest_log_date')
    def get_latest_log_date():
        house_id = request.args.get('house_id')
        if not house_id:
            return jsonify({}), 400

        flock = Flock.query.filter_by(house_id=house_id, status='Active').first()
        if not flock:
            return jsonify({}), 404

        latest_log = DailyLog.query.filter_by(flock_id=flock.id).order_by(DailyLog.date.desc()).first()

        if latest_log:
            return jsonify({'latest_date': latest_log.date.strftime('%Y-%m-%d')}), 200
        else:
            return jsonify({'latest_date': None}), 200

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

        # Enhance with new values for Smart Summary validation
        yesterday_mortality_m = yesterday_log.mortality_male if yesterday_log else 0
        yesterday_mortality_f = yesterday_log.mortality_female if yesterday_log else 0
        yesterday_eggs = yesterday_log.eggs_collected if yesterday_log else 0
        yesterday_water = yesterday_log.water_intake_calculated if yesterday_log else 0
        yesterday_water_r1 = yesterday_log.water_reading_1 if yesterday_log else 0

        # Calculate yesterday's stock for accurate percentage
        y_cum_mort_m = sum((l.mortality_male or 0) + (l.culls_male or 0) for l in all_prev_logs if l.date < (log_date - timedelta(days=1)))
        y_cum_mort_f = sum((l.mortality_female or 0) + (l.culls_female or 0) for l in all_prev_logs if l.date < (log_date - timedelta(days=1)))
        y_stock_m = (flock.intake_male or 0) - y_cum_mort_m
        y_stock_f = (flock.intake_female or 0) - y_cum_mort_f

        yesterday_egg_pct = (yesterday_eggs / y_stock_f * 100) if y_stock_f > 0 else 0
        yesterday_mort_m_pct = (yesterday_mortality_m / y_stock_m * 100) if y_stock_m > 0 else 0
        yesterday_mort_f_pct = (yesterday_mortality_f / y_stock_f * 100) if y_stock_f > 0 else 0

        # Current flock age in weeks
        flock_age_days = (log_date - flock.intake_date).days + 1
        flock_age_weeks = flock_age_days / 7.0

        data = {
            'current_stock_m': current_stock_m,
            'current_stock_f': current_stock_f,
            'yesterday_feed_m': yesterday_log.feed_male_gp_bird if yesterday_log else 0,
            'yesterday_feed_f': yesterday_log.feed_female_gp_bird if yesterday_log else 0,
            'day_minus_2_feed_m': day_minus_2_log.feed_male_gp_bird if day_minus_2_log else 0,
            'day_minus_2_feed_f': day_minus_2_log.feed_female_gp_bird if day_minus_2_log else 0,
            'yesterday_eggs': yesterday_eggs,
            'yesterday_egg_pct': yesterday_egg_pct,
            'yesterday_water': yesterday_water,
            'yesterday_water_r1': yesterday_water_r1,
            'flock_age_weeks': flock_age_weeks,
            'yesterday_mortality_m': yesterday_mortality_m,
            'yesterday_mortality_f': yesterday_mortality_f,
            'yesterday_mort_m_pct': yesterday_mort_m_pct,
            'yesterday_mort_f_pct': yesterday_mort_f_pct
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
                    'males_in_flock', 'males_out_flock', 'females_in_flock', 'females_out_flock',
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

    @app.route('/api/flock/<int:flock_id>/export_csv')
    def export_flock_csv(flock_id):
        # Both Farm and Executive roles can view flock details, so both should be able to export
        if not current_user.role == 'Admin' and current_user.role not in ALLOWED_EXPORT_ROLES:
            flash('Access Denied.', 'danger')
            return redirect(get_dashboard_url(current_user))

        flock = db.session.get(Flock, flock_id)
        if not flock:
            flash('Flock not found', 'danger')
            return redirect(get_dashboard_url(current_user))

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
            "Males In", "Males Out", "Females In", "Females Out",
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

        all_standards = Standard.query.all()
        daily_stats = enrich_flock_data(flock, all_logs, hatch_records, all_standards=all_standards)

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
                data['metrics'].setdefault('std_egg_prod', []).append(round(d.get('std_egg_prod', 0.0), 2))
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
                data['metrics'].setdefault('std_egg_prod', []).append(round(a.get('std_egg_prod', 0.0), 2))
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

    @app.route('/api/test_notification', methods=['POST'])
    @login_required
    def test_notification():
        user_id = current_user.id
        # Call the push alert function
        try:
            success = send_push_alert(user_id, "Test Notification", "Your device is successfully linked!", url=get_dashboard_url(current_user))
            if success:
                return jsonify({'success': True, 'message': 'Notification sent successfully.'}), 200
            else:
                return jsonify({'success': False, 'message': 'No valid push subscriptions found or all failed. Please re-subscribe.'}), 400
        except Exception as e:
            app.logger.error(f"Failed to send test push: {e}")
            return jsonify({'error': str(e)}), 500

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

    from app.extensions import limiter

    @app.route('/api/version')
    @limiter.exempt
    def get_version():
        return jsonify({'version': APP_VERSION})

    @app.route('/api/check_grading_exists')
    @login_required
    def check_grading_exists():
        house_id = request.args.get('house_id', type=int)
        age_week = request.args.get('age_week', type=int)

        if not house_id or age_week is None:
            return jsonify({'error': 'Missing parameters'}), 400

        exists = FlockGrading.query.filter_by(house_id=house_id, age_week=age_week).first() is not None
        return jsonify({'exists': exists})

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

        weeks = calculate_bio_week(flock.intake_date, target_date)

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
            last_weighing_week = calculate_bio_week(flock.intake_date, last_log.date)

        response_data = {
            'week': weeks,
            'std_bw_male': std.std_bw_male if std else '',
            'std_bw_female': std.std_bw_female if std else '',
            'last_weighing_date': last_weighing_date,
            'last_weighing_week': last_weighing_week
        }
        return jsonify(response_data)
