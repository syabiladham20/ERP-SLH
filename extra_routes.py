7964-                           selected_year=selected_year,
7965-                           active_tab=active_tab)
7966-
7967-
7968-@app.route('/executive/flock_select')
7969:def flock_detail_readonly_select():
7970-    # Role Check: Admin or Management
7971-    if not session.get('is_admin') and session.get('user_role') != 'Management':
7972-        flash("Access Denied: Executive View Only.", "danger")
7973-        return redirect(url_for('index'))
7974-
7975-    active_flocks = Flock.query.options(joinedload(Flock.house)).filter_by(status='Active').all()
7976-    active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else ''))
7977-
7978-    if not active_flocks:
7979-        flash("No active flocks found.", "warning")
7980-        return redirect(url_for('executive_dashboard'))
7981-
7982-    return render_template('flock_detail_readonly_select.html', active_flocks=active_flocks)
7983-
7984-@app.route('/executive/flock/<int:id>')
7985-def executive_flock_detail(id):
7986-    # Role Check: Admin or Management
7987-    if not session.get('is_admin') and session.get('user_role') != 'Management':
7988-        flash("Access Denied: Executive View Only.", "danger")
7989-        return redirect(url_for('index'))
7990-
7991-    active_flocks = Flock.query.options(joinedload(Flock.house)).filter_by(status='Active').all()
7992-    active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else ''))
7993-
7994-    flock = Flock.query.options(joinedload(Flock.house)).filter_by(id=id).first_or_404()
7995-    logs = DailyLog.query.options(joinedload(DailyLog.partition_weights), joinedload(DailyLog.photos), joinedload(DailyLog.clinical_notes_list)).filter_by(flock_id=id).order_by(DailyLog.date.asc()).all()
7996-
7997-    gs = GlobalStandard.query.first()
7998-    if not gs:
7999-        gs = GlobalStandard()
8000-        db.session.add(gs)
8001-        db.session.commit()
8002-
8003-    # --- Standards Setup ---
8004-    all_standards = Standard.query.all()
8005-    std_map = {getattr(s, 'week'): s for s in all_standards if hasattr(s, 'week')} # Bio Map
8006-    prod_std_map = {getattr(s, 'production_week'): s for s in all_standards if hasattr(s, 'production_week') and getattr(s, 'production_week')} # Prod Map
8007-
8008-    std_hatch_map = {getattr(s, 'week'): (getattr(s, 'std_hatchability', 0.0) or 0.0) for s in all_standards if hasattr(s, 'week')}
8009-
8010-    # --- Fetch Hatch Data ---
8011-    hatch_records = Hatchability.query.filter_by(flock_id=id).order_by(Hatchability.setting_date.desc()).all()
8012-
8013-    # --- Metrics Engine ---
8014-    daily_stats = enrich_flock_data(flock, logs, hatch_records)
8015-
8016-    # --- Calculate Summary Tab Data ---
8017-    summary_dashboard, summary_table = calculate_flock_summary(flock, daily_stats)
8018-
8019-    # Inject Shifted Standard
8020-    for d in daily_stats:
8021-        # Biological Standards (Mortality, BW)
8022-        std_bio = std_map.get(d['week'])
8023-        d['std_mortality_male'] = (std_bio.std_mortality_male if std_bio and std_bio.std_mortality_male is not None else 0.0)
8024-        d['std_mortality_female'] = (std_bio.std_mortality_female if std_bio and std_bio.std_mortality_female is not None else 0.0)
8025-
8026-        # Production Standards (Egg Prod)
8027-        prod_std = None
8028-        if d.get('production_week'):
8029-            prod_std = prod_std_map.get(d['production_week'])
8030-
8031-        d['std_egg_prod'] = (prod_std.std_egg_prod if prod_std and prod_std.std_egg_prod is not None else 0.0)
8032-        d['std_hatching_egg_pct'] = (prod_std.std_hatching_egg_pct if prod_std and prod_std.std_hatching_egg_pct is not None else 0.0)
8033-
8034-    weekly_stats = aggregate_weekly_metrics(daily_stats)
8035-
8036-    for ws in weekly_stats:
8037-        # Biological Standards
8038-        std_bio = std_map.get(ws['week'])
8039-        ws['std_mortality_male'] = (std_bio.std_mortality_male if std_bio and std_bio.std_mortality_male is not None else 0.0)
8040-        ws['std_mortality_female'] = (std_bio.std_mortality_female if std_bio and std_bio.std_mortality_female is not None else 0.0)
8041-
8042-        # Production Standards
8043-        prod_std = None
8044-        if ws.get('production_week'):
8045-            prod_std = prod_std_map.get(ws['production_week'])
8046-
8047-        ws['std_egg_prod'] = (prod_std.std_egg_prod if prod_std and prod_std.std_egg_prod is not None else 0.0)
8048-        ws['std_hatching_egg_pct'] = (prod_std.std_hatching_egg_pct if prod_std and prod_std.std_hatching_egg_pct is not None else 0.0)
8049-
8050-    medications = Medication.query.filter_by(flock_id=id).all()
8051-    vacs = Vaccine.query.filter_by(flock_id=id).filter(Vaccine.actual_date != None).all()
8052-
8053-    # 1. Enriched Logs
8054-    enriched_logs = []
8055-    def scale_pct(val):
8056-        if val is None: return None
8057-        if 0 < val <= 1.0: return val * 100.0
8058-        return val
8059-
8060-    for d in daily_stats:
8061-        log = d['log']
8062-        lighting_hours = 0
8063-        if log.light_on_time and log.light_off_time:
8064-            try:
8065-                fmt = '%H:%M'
8066-                t1 = datetime.strptime(log.light_on_time, fmt)
8067-                t2 = datetime.strptime(log.light_off_time, fmt)
8068-                diff = (t2 - t1).total_seconds() / 3600
8069-                if diff < 0: diff += 24
8070-                lighting_hours = round(diff, 1)
8071-            except: pass
8072-
8073-        active_meds = []
8074-        for m in medications:
8075-            if m.start_date <= log.date:
8076-                if m.end_date is None or m.end_date >= log.date:
8077-                    active_meds.append(m.drug_name)
8078-        meds_str = ", ".join(active_meds)
8079-
8080-        cleanup_duration_mins = None
8081-        if log.feed_cleanup_start and log.feed_cleanup_end:
8082-            try:
8083-                from analytics import calculate_feed_cleanup_duration
8084-                cleanup_duration_mins = calculate_feed_cleanup_duration(log.feed_cleanup_start, log.feed_cleanup_end)
8085-            except Exception:
8086-                pass
8087-        feed_cleanup_hours = round(cleanup_duration_mins / 60.0, 1) if cleanup_duration_mins else None
8088-
8089-        enriched_logs.append({
8090-            'log': log,
8091-            'stock_male': d['stock_male_start'],
8092-            'stock_female': d['stock_female_start'],
8093-            'lighting_hours': lighting_hours,
8094-            'medications': meds_str,
8095-            'egg_prod_pct': d['egg_prod_pct'],
8096-            'total_feed': d['feed_total_kg'],
8097-            'feed_cleanup_hours': feed_cleanup_hours,
8098-            'egg_data': {
8099-                'jumbo': d['cull_eggs_jumbo'],
8100-                'jumbo_pct': d['cull_eggs_jumbo_pct'],
8101-                'small': d['cull_eggs_small'],
8102-                'small_pct': d['cull_eggs_small_pct'],
8103-                'crack': d['cull_eggs_crack'],
8104-                'crack_pct': d['cull_eggs_crack_pct'],
8105-                'abnormal': d['cull_eggs_abnormal'],
8106-                'abnormal_pct': d['cull_eggs_abnormal_pct'],
8107-                'hatching': d['hatch_eggs'],
8108-                'hatching_pct': d['hatch_egg_pct'],
8109-                'total_culls': d['cull_eggs_total'],
8110-                'total_culls_pct': d['cull_eggs_pct']
8111-            }
8112-        })
8113-
8114-    # 2. Weekly Data
8115-    weekly_data = []
8116-    for ws in weekly_stats:
8117-        w_item = {
8118-            'week': ws['week'],
8119-            'mortality_male': ws['mortality_male'],
8120-            'mortality_female': ws['mortality_female'],
8121-            'culls_male': ws['culls_male'],
8122-            'culls_female': ws['culls_female'],
8123-            'eggs': ws['eggs_collected'],
8124-            'hatch_eggs_sum': ws['hatch_eggs'],
8125-            'cull_eggs_total': ws['cull_eggs_jumbo'] + ws['cull_eggs_small'] + ws['cull_eggs_crack'] + ws['cull_eggs_abnormal'],
8126-            'mort_pct_m': ws['mortality_male_pct'],
8127-            'mort_pct_f': ws['mortality_female_pct'],
8128-            'cull_pct_m': ws['culls_male_pct'],
8129-            'cull_pct_f': ws['culls_female_pct'],
8130-            'egg_prod_pct': ws['egg_prod_pct'],
8131-            'hatching_egg_pct': ws['hatch_egg_pct'],
8132-            'cull_eggs_jumbo': ws['cull_eggs_jumbo'],
8133-            'cull_eggs_jumbo_pct': ws['cull_eggs_jumbo_pct'] * 100 if ws.get('cull_eggs_jumbo_pct') else 0,
8134-            'cull_eggs_small': ws['cull_eggs_small'],
8135-            'cull_eggs_small_pct': ws['cull_eggs_small_pct'] * 100 if ws.get('cull_eggs_small_pct') else 0,
8136-            'cull_eggs_crack': ws['cull_eggs_crack'],
8137-            'cull_eggs_crack_pct': ws['cull_eggs_crack_pct'] * 100 if ws.get('cull_eggs_crack_pct') else 0,
8138-            'cull_eggs_abnormal': ws['cull_eggs_abnormal'],
8139-            'cull_eggs_abnormal_pct': ws['cull_eggs_abnormal_pct'] * 100 if ws.get('cull_eggs_abnormal_pct') else 0,
8140-            'avg_bw_male': round_to_whole(ws['body_weight_male']),
8141-            'avg_bw_female': round_to_whole(ws['body_weight_female']),
8142-            'notes': ws['notes'],
8143-            'photos': ws['photos']
8144-        }
8145-        weekly_data.append(w_item)
8146-
8147-    # 3. Chart Data (Daily)
8148-    chart_data = {
8149-        'dates': [d['date'].strftime('%Y-%m-%d') for d in daily_stats],
8150-        'ages': [d['log'].age_week_day for d in daily_stats],
8151-        'mortality_cum_male': [round(d['mortality_cum_male_pct'], 2) for d in daily_stats],
8152-        'mortality_cum_female': [round(d['mortality_cum_female_pct'], 2) for d in daily_stats],
8153-        'mortality_daily_male': [round(d['mortality_male_pct'], 2) for d in daily_stats],
8154-        'mortality_daily_female': [round(d['mortality_female_pct'], 2) for d in daily_stats],
8155-        'std_mortality_male': [round(d['std_mortality_male'], 3) for d in daily_stats],
8156-        'std_mortality_female': [round(d['std_mortality_female'], 3) for d in daily_stats],
8157-        'culls_daily_male': [round(d['culls_male_pct'], 2) for d in daily_stats],
8158-        'culls_daily_female': [round(d['culls_female_pct'], 2) for d in daily_stats],
8159-        'egg_prod': [round(d['egg_prod_pct'], 2) for d in daily_stats],
8160-        'std_egg_prod': [round(d['std_egg_prod'], 2) for d in daily_stats],
8161-        'hatch_egg_pct': [round(d['hatch_egg_pct'], 2) for d in daily_stats],
8162-        'std_hatching_egg_pct': [round(d['std_hatching_egg_pct'], 2) for d in daily_stats],
8163-        'cull_eggs_jumbo_pct': [round(d['cull_eggs_jumbo_pct'], 2) for d in daily_stats],
8164-        'cull_eggs_small_pct': [round(d['cull_eggs_small_pct'], 2) for d in daily_stats],
8165-        'cull_eggs_crack_pct': [round(d['cull_eggs_crack_pct'], 2) for d in daily_stats],
8166-        'cull_eggs_abnormal_pct': [round(d['cull_eggs_abnormal_pct'], 2) for d in daily_stats],
8167-        'male_ratio': [round(d['male_ratio_stock'], 2) if d['male_ratio_stock'] else 0 for d in daily_stats],
8168-        'bw_male_std': [d['log'].standard_bw_male if d['log'].standard_bw_male > 0 else None for d in daily_stats],
8169-        'bw_female_std': [d['log'].standard_bw_female if d['log'].standard_bw_female > 0 else None for d in daily_stats],
8170-        'unif_male': [scale_pct(d['uniformity_male']) if d['uniformity_male'] > 0 else None for d in daily_stats],
8171-        'unif_female': [scale_pct(d['uniformity_female']) if d['uniformity_female'] > 0 else None for d in daily_stats],
8172-        'bw_f': [d['body_weight_female'] if d['body_weight_female'] > 0 else None for d in daily_stats],
8173-        'bw_m': [d['body_weight_male'] if d['body_weight_male'] > 0 else None for d in daily_stats],
8174-        'water_per_bird': [round(d['water_per_bird'], 1) for d in daily_stats],
8175-        'feed_male_gp_bird': [round(d['feed_male_gp_bird'], 1) for d in daily_stats],
8176-        'feed_female_gp_bird': [round(d['feed_female_gp_bird'], 1) for d in daily_stats],
8177-        'flushing': [d['log'].flushing for d in daily_stats],
8178-        'notes': [],
8179-        'medication_active': [],
8180-        'medication_names': []
8181-    }
8182-
8183-    for i in range(1, 9):
8184-        chart_data[f'bw_M{i}'] = []
8185-        chart_data[f'bw_F{i}'] = []
8186-
8187-    for d in daily_stats:
8188-        log = d['log']
8189-        p_map = {pw.partition_name: pw.body_weight for pw in log.partition_weights}
8190-        for i in range(1, 9):
8191-            val_m = p_map.get(f'M{i}', 0)
8192-            if val_m == 0 and i <= 2: val_m = getattr(log, f'bw_male_p{i}', 0)
8193-            chart_data[f'bw_M{i}'].append(val_m if val_m > 0 else None)
8194-            val_f = p_map.get(f'F{i}', 0)
8195-            if val_f == 0 and i <= 4: val_f = getattr(log, f'bw_female_p{i}', 0)
8196-            chart_data[f'bw_F{i}'].append(val_f if val_f > 0 else None)
8197-
8198-        note_obj = None
8199-
8200-        # Construct Note
8201-        note_parts = []
8202-        if log.flushing: note_parts.append("[FLUSHING]")
8203-        if log.clinical_notes: note_parts.append(log.clinical_notes)
8204-
8205-        # Meds
8206-        active_meds = [m.drug_name for m in medications if m.start_date <= log.date and (m.end_date is None or m.end_date >= log.date)]
8207-        chart_data['medication_active'].append(len(active_meds) > 0)
8208-        chart_data['medication_names'].append(", ".join(active_meds) if active_meds else "")
8209-
8210-        # User requested to remove medication from notes, so we don't append to note_parts
8211-        # if active_meds: note_parts.append("Meds: " + ", ".join(active_meds))
8212-
8213-        # Vacs
8214-        done_vacs = [v.vaccine_name for v in vacs if v.actual_date == log.date]
8215-        if done_vacs: note_parts.append("Vac: " + ", ".join(done_vacs))
8216-
8217-        has_photos = len(log.photos) > 0
8218-        if note_parts or has_photos:
8219-            photo_list = []
8220-            for p in log.photos:
8221-                photo_list.append({
8222-                    'url': url_for('uploaded_file', filename=os.path.basename(p.file_path)),
8223-                    'name': p.original_filename or 'Photo'
8224-                })
8225-
8226-            note_obj = {
8227-                'note': " | ".join(note_parts),
8228-                'photos': photo_list
8229-            }
8230-
8231-        chart_data['notes'].append(note_obj)
8232-
8233-    # 4. Chart Data (Weekly)
8234-    daily_by_week = {}
8235-    for d in daily_stats:
8236-        if d['week'] not in daily_by_week: daily_by_week[d['week']] = []
8237-        daily_by_week[d['week']].append(d)
8238-
8239-    weekly_map = {ws['week']: ws for ws in weekly_stats}
8240-    chart_data_weekly = {
8241-        'dates': [],
8242-        'ages': [],
8243-        'mortality_cum_male': [], 'mortality_cum_female': [],
8244-        'mortality_weekly_male': [], 'mortality_weekly_female': [],
8245-        'std_mortality_male': [], 'std_mortality_female': [],
8246-        'culls_weekly_male': [], 'culls_weekly_female': [],
8247-        'avg_bw_male': [], 'avg_bw_female': [],
8248-        'egg_prod': [],
8249-        'bw_male_std': [], 'bw_female_std': [],
8250-        'unif_male': [], 'unif_female': [],
8251-        'notes': []
8252-    }
8253-    for i in range(1, 9):
8254-        chart_data_weekly[f'bw_M{i}'] = []
8255-        chart_data_weekly[f'bw_F{i}'] = []
8256-
8257-    for w in sorted(weekly_map.keys()):
8258-        ws = weekly_map[w]
8259-        last_day = daily_by_week[w][-1]
8260-
8261-        chart_data_weekly['dates'].append(f"Week {w}")
8262-        chart_data_weekly['mortality_cum_male'].append(round(last_day['mortality_cum_male_pct'], 2))
8263-        chart_data_weekly['mortality_cum_female'].append(round(last_day['mortality_cum_female_pct'], 2))
8264-        chart_data_weekly['mortality_weekly_male'].append(round(ws['mortality_male_pct'], 2))
8265-        chart_data_weekly['mortality_weekly_female'].append(round(ws['mortality_female_pct'], 2))
8266-        chart_data_weekly['culls_weekly_male'].append(round(ws['culls_male_pct'], 2))
8267-        chart_data_weekly['culls_weekly_female'].append(round(ws['culls_female_pct'], 2))
8268-        chart_data_weekly['avg_bw_male'].append(round_to_whole(ws['body_weight_male']) if ws['body_weight_male'] > 0 else None)
8269-        chart_data_weekly['avg_bw_female'].append(round_to_whole(ws['body_weight_female']) if ws['body_weight_female'] > 0 else None)
8270-        chart_data_weekly['egg_prod'].append(round(ws['egg_prod_pct'], 2))
8271-        chart_data_weekly['std_egg_prod'] = chart_data_weekly.get('std_egg_prod', [])
8272-        chart_data_weekly['std_egg_prod'].append(round(ws['std_egg_prod'], 2))
8273-
8274-        chart_data_weekly['hatch_egg_pct'] = chart_data_weekly.get('hatch_egg_pct', [])
8275-        chart_data_weekly['hatch_egg_pct'].append(round(ws['hatch_egg_pct'], 2))
8276-
8277-        chart_data_weekly['std_hatching_egg_pct'] = chart_data_weekly.get('std_hatching_egg_pct', [])
8278-        chart_data_weekly['std_hatching_egg_pct'].append(round(ws['std_hatching_egg_pct'], 2))
8279-
8280-        chart_data_weekly['cull_eggs_jumbo_pct'] = chart_data_weekly.get('cull_eggs_jumbo_pct', [])
8281-        chart_data_weekly['cull_eggs_jumbo_pct'].append(round(ws['cull_eggs_jumbo_pct'], 2))
8282-
8283-        chart_data_weekly['cull_eggs_small_pct'] = chart_data_weekly.get('cull_eggs_small_pct', [])
8284-        chart_data_weekly['cull_eggs_small_pct'].append(round(ws['cull_eggs_small_pct'], 2))
8285-
8286-        chart_data_weekly['cull_eggs_crack_pct'] = chart_data_weekly.get('cull_eggs_crack_pct', [])
8287-        chart_data_weekly['cull_eggs_crack_pct'].append(round(ws['cull_eggs_crack_pct'], 2))
8288-
8289-        chart_data_weekly['cull_eggs_abnormal_pct'] = chart_data_weekly.get('cull_eggs_abnormal_pct', [])
8290-        chart_data_weekly['cull_eggs_abnormal_pct'].append(round(ws['cull_eggs_abnormal_pct'], 2))
8291-
8292-        # Standard BW - Use Biological Age (w)
8293-        std_bio = std_map.get(w)
8294-        chart_data_weekly['bw_male_std'].append(std_bio.std_bw_male if std_bio and std_bio.std_bw_male > 0 else None)
8295-        chart_data_weekly['bw_female_std'].append(std_bio.std_bw_female if std_bio and std_bio.std_bw_female > 0 else None)
8296-
8297-        chart_data_weekly['unif_male'].append(scale_pct(ws['uniformity_male']) if ws['uniformity_male'] > 0 else None)
8298-        chart_data_weekly['unif_female'].append(scale_pct(ws['uniformity_female']) if ws['uniformity_female'] > 0 else None)
8299-
8300-        chart_data_weekly['water_per_bird'] = chart_data_weekly.get('water_per_bird', [])
8301-        chart_data_weekly['water_per_bird'].append(round(ws['water_per_bird'], 1))
8302-
8303-        chart_data_weekly['feed_male_gp_bird'] = chart_data_weekly.get('feed_male_gp_bird', [])
8304-        chart_data_weekly['feed_male_gp_bird'].append(round(ws['feed_male_gp_bird'], 1))
8305-
8306-        chart_data_weekly['feed_female_gp_bird'] = chart_data_weekly.get('feed_female_gp_bird', [])
8307-        chart_data_weekly['feed_female_gp_bird'].append(round(ws['feed_female_gp_bird'], 1))
8308-
8309-        for i in range(1, 9):
8310-            chart_data_weekly[f'bw_M{i}'].append(None)
8311-            chart_data_weekly[f'bw_F{i}'].append(None)
8312-
8313-        # Aggregate Weekly Notes/Photos
8314-        week_notes = []
8315-        week_photos = []
8316-
8317-        # From Daily Logs
8318-        if w in daily_by_week:
8319-            week_logs_data = daily_by_week[w]
8320-            if week_logs_data:
8321-                w_start = week_logs_data[0]['date']
8322-                w_end = week_logs_data[-1]['date']
8323-
8324-                for d in week_logs_data:
8325-                    log = d['log']
8326-                    if log.clinical_notes:
8327-                        week_notes.append(f"{log.date.strftime('%d/%m')}: {log.clinical_notes}")
8328-
8329-                    for p in log.photos:
8330-                        week_photos.append({
8331-                            'url': url_for('uploaded_file', filename=os.path.basename(p.file_path)),
8332-                            'name': f"{log.date.strftime('%d/%m')} {p.original_filename or 'Photo'}"
8333-                        })
8334-
8335-                # Meds
8336-                w_meds = set()
8337-                for m in medications:
8338-                    if m.start_date <= w_end and (m.end_date is None or m.end_date >= w_start):
8339-                        w_meds.add(m.drug_name)
8340-                if w_meds: week_notes.append("Meds: " + ", ".join(w_meds))
8341-
8342-                # Vacs
8343-                w_vacs = set()
8344-                for v in vacs:
8345-                    if v.actual_date and w_start <= v.actual_date <= w_end:
8346-                        w_vacs.add(v.vaccine_name)
8347-                if w_vacs: week_notes.append("Vac: " + ", ".join(w_vacs))
8348-
8349-        if week_notes or week_photos:
8350-            chart_data_weekly['notes'].append({
8351-                'note': " | ".join(week_notes),
8352-                'photos': week_photos
8353-            })
8354-        else:
8355-            chart_data_weekly['notes'].append(None)
8356-
8357-    # 5. Current Stats
8358-    if daily_stats:
8359-        last = daily_stats[-1]
8360-        current_stats = {
8361-            'male_prod': last.get('stock_male_prod_end', 0),
8362-            'female_prod': last.get('stock_female_prod_end', 0),
8363-            'male_hosp': last.get('stock_male_hosp_end', 0),
8364-            'female_hosp': last.get('stock_female_hosp_end', 0),
8365-            'male_ratio': last['male_ratio_stock'] if last.get('male_ratio_stock') else 0
8366-        }
8367-    else:
8368-        current_stats = {
8369-            'male_prod': flock.intake_male,
8370-            'female_prod': flock.intake_female,
8371-            'male_hosp': 0,
8372-            'female_hosp': 0,
8373-            'male_ratio': (flock.intake_male / flock.intake_female * 100) if flock.intake_female > 0 else 0
8374-        }
8375-
8376-    weekly_data.reverse()
8377-
8378-    # Pre-check available reports for this flock
8379-    from werkzeug.utils import secure_filename
8380-    reports_dir = os.path.join(app.root_path, 'static', 'reports')
8381-    available_reports = set()
8382-    if os.path.exists(reports_dir):
8383-        prefix_to_match = f"_{secure_filename(flock.house.name)}_"
8384-        for f in os.listdir(reports_dir):
8385-            if prefix_to_match in f and f.endswith(".jpg"):
8386-                date_str = f.split("_")[0]
8387-                available_reports.add(date_str)
8388-
8389-    return render_template('flock_detail_readonly.html',
8390-                           flock=flock,
8391-                           available_reports=available_reports,
8392-                           logs=list(reversed(enriched_logs)),
8393-                           weekly_data=weekly_data,
8394-                           chart_data=chart_data,
8395-                           chart_data_weekly=chart_data_weekly,
8396-                           current_stats=current_stats,
8397-                           global_std=gs,
8398-                           active_flocks=active_flocks,
8399-                           hatch_records=hatch_records,
8400-                           summary_dashboard=summary_dashboard,
8401-                           summary_table=summary_table,
8402-                           std_hatch_map=std_hatch_map)
8403-
8404-
8405-@app.route('/api/floating_notes/<int:flock_id>', methods=['GET'])
8406-@dept_required(['Farm', 'Admin', 'Management'])
8407-def get_floating_notes(flock_id):
8408-    notes = FloatingNote.query.filter_by(flock_id=flock_id).all()
8409-    result = []
8410-    for note in notes:
8411-        result.append({
8412-            'id': note.id,
8413-            'chart_id': note.chart_id,
8414-            'x_value': note.x_value,
8415-            'y_value': note.y_value,
8416-            'content': note.content
8417-        })
8418-    return jsonify(result)
8419-
8420-@app.route('/api/floating_notes', methods=['POST'])
8421-@dept_required(['Farm', 'Admin'])
8422-def create_floating_note():
8423-    data = request.json
8424-    try:
8425-        new_note = FloatingNote(
8426-            flock_id=data['flock_id'],
8427-            chart_id=data['chart_id'],
8428-            x_value=data['x_value'],
8429-            y_value=float(data['y_value']),
8430-            content=data['content']
8431-        )
8432-        db.session.add(new_note)
8433-        db.session.commit()
8434-        return jsonify({'success': True, 'id': new_note.id}), 201
8435-    except Exception as e:
8436-        db.session.rollback()
8437-        return jsonify({'success': False, 'error': str(e)}), 400
8438-
8439-@app.route('/api/floating_notes/<int:note_id>', methods=['DELETE'])
8440-@dept_required(['Farm', 'Admin'])
8441-def delete_floating_note(note_id):
8442-    try:
8443-        note = FloatingNote.query.get_or_404(note_id)
8444-        db.session.delete(note)
8445-        db.session.commit()
8446-        return jsonify({'success': True}), 200
8447-    except Exception as e:
8448-        db.session.rollback()
8449-        return jsonify({'success': False, 'error': str(e)}), 400
8450-
8451-
8452-@app.route('/api/daily_log/trend')
8453-@login_required
8454-def api_daily_log_trend():
8455-    flock_id = request.args.get('flock_id', type=int)
8456-    end_date_str = request.args.get('date')
8457-    if not flock_id or not end_date_str:
8458-        return jsonify({'error': 'Missing parameters'}), 400
8459-
8460-    try:
8461-        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
8462-    except ValueError:
8463-        return jsonify({'error': 'Invalid date format'}), 400
8464-
8465-    start_date = end_date - timedelta(days=70) # Fetch up to 10 weeks
8466-
8467-    flock = Flock.query.get_or_404(flock_id)
8468-
8469-    logs = DailyLog.query.filter(
