@app.route('/executive/flock_select')
def flock_detail_readonly_select():
    # Role Check: Admin or Management
    if not session.get('is_admin') and session.get('user_role') != 'Management':
        flash("Access Denied: Executive View Only.", "danger")
        return redirect(url_for('index'))

    active_flocks = Flock.query.options(joinedload(Flock.house)).filter_by(status='Active').all()
    active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else ''))

    if not active_flocks:
        flash("No active flocks found.", "warning")
        return redirect(url_for('executive_dashboard'))

    return render_template('flock_detail_readonly_select.html', active_flocks=active_flocks)

@app.route('/executive/flock/<int:id>')
def executive_flock_detail(id):
    # Role Check: Admin or Management
    if not session.get('is_admin') and session.get('user_role') != 'Management':
        flash("Access Denied: Executive View Only.", "danger")
        return redirect(url_for('index'))

    active_flocks = Flock.query.options(joinedload(Flock.house)).filter_by(status='Active').all()
    active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else ''))

    flock = Flock.query.options(joinedload(Flock.house)).filter_by(id=id).first_or_404()
    logs = DailyLog.query.options(joinedload(DailyLog.partition_weights), joinedload(DailyLog.photos), joinedload(DailyLog.clinical_notes_list)).filter_by(flock_id=id).order_by(DailyLog.date.asc()).all()

    gs = GlobalStandard.query.first()
    if not gs:
        gs = GlobalStandard()
        db.session.add(gs)
        db.session.commit()

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
            'stock_male': d['stock_male_start'],
            'stock_female': d['stock_female_start'],
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
        'water_per_bird': [round(d['water_per_bird'], 1) for d in daily_stats],
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
        chart_data_weekly['water_per_bird'].append(round(ws['water_per_bird'], 1))

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
        db.session.commit()
        return jsonify({'success': True, 'id': new_note.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/floating_notes/<int:note_id>', methods=['DELETE'])
@dept_required(['Farm', 'Admin'])
def delete_floating_note(note_id):
    try:
        note = FloatingNote.query.get_or_404(note_id)
        db.session.delete(note)
        db.session.commit()
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

    stock_m = end_day_log.get('stock_male_start', 0)
    stock_f = end_day_log.get('stock_female_start', 0)
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

    report_info = {
        'empty': False,
        'house_name': flock.house.name,
        'age_week': end_day_log.get('week', 0),
        'phase': getattr(flock, 'calculated_phase', flock.phase),
        'date': end_date.strftime('%d-%m-%Y'),
        'lighting_hours': lighting_hours,
        'feed_cleanup_hours': feed_cleanup_hours,
        'stock_m': stock_m,
        'stock_f': stock_f,
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
