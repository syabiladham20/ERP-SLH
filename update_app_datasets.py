import re

with open('app.py', 'r') as f:
    content = f.read()

new_get_chart_data = """def get_chart_data(flock_id):
    flock = Flock.query.get_or_404(flock_id)

    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    mode = request.args.get('mode', 'daily') # 'daily', 'weekly', 'monthly'

    hatch_records = Hatchability.query.filter_by(flock_id=flock_id).all()
    all_logs = DailyLog.query.options(joinedload(DailyLog.photos), joinedload(DailyLog.clinical_notes_list)).filter_by(flock_id=flock_id).order_by(DailyLog.date.asc()).all()

    # Fetch Health Data
    meds = Medication.query.filter_by(flock_id=flock_id).all()
    vacs = Vaccine.query.filter_by(flock_id=flock_id).filter(Vaccine.actual_date != None).all()

    daily_stats = enrich_flock_data(flock, all_logs, hatch_records)

    filtered_daily = []
    for d in daily_stats:
        if start_date_str and d['date'] < datetime.strptime(start_date_str, '%Y-%m-%d').date(): continue
        if end_date_str and d['date'] > datetime.strptime(end_date_str, '%Y-%m-%d').date(): continue
        filtered_daily.append(d)

    labels = []

    # We will build dataset groups for each chart: general, hatching, water, feed, bw_male, bw_female
    # Each group will have its own 'labels' and 'datasets'

    charts = {
        'general': {'labels': [], 'datasets': []},
        'hatching': {'labels': [], 'datasets': []},
        'water': {'labels': [], 'datasets': []},
        'feed': {'labels': [], 'datasets': []},
        'bw_male': {'labels': [], 'datasets': []},
        'bw_female': {'labels': [], 'datasets': []}
    }

    # Helper maps to build datasets
    def init_dataset(label, color, yAxisID, type_='line', fill=False, tension=0.1, borderDash=None, hidden=False, stack=None, is_bar=False):
        ds = {
            "label": label,
            "data": [],
            "borderColor": color,
            "backgroundColor": color if is_bar else color + "33", # Add some transparency for fill
            "yAxisID": yAxisID,
            "tension": tension,
            "hidden": hidden,
            "type": type_
        }
        if fill: ds["fill"] = True
        if borderDash: ds["borderDash"] = borderDash
        if stack: ds["stack"] = stack
        return ds

    # General Chart
    ds_egg_prod = init_dataset("Egg Prod %", "#206bc4", "y", "line", False)
    ds_std_egg_prod = init_dataset("Std Egg Prod %", "#206bc4", "y", "line", False, borderDash=[5,5], hidden=True)
    ds_mort_f = init_dataset("Fem Depletion %", "#d63939", "y1", "bar", True, is_bar=True)
    ds_mort_m = init_dataset("Male Depletion %", "#f59f00", "y1", "bar", True, is_bar=True)
    ds_std_mort_f = init_dataset("Std Fem Depletion %", "#d63939", "y1", "line", False, borderDash=[5,5], hidden=True)

    # Hatching Chart
    ds_hatch_egg = init_dataset("Hatching Egg %", "#2fb344", "y", "line", False)
    ds_std_hatch_egg = init_dataset("Std Hatching Egg %", "#2fb344", "y", "line", False, borderDash=[5,5], hidden=True)

    # Water Chart
    ds_water = init_dataset("Water Intake (ml/bird)", "#4299e1", "y", "line", True)
    ds_water_ratio = init_dataset("Water:Feed Ratio", "#6574cd", "y1", "line", False)

    # Feed Chart
    ds_feed_f = init_dataset("Female Feed (g/bird)", "#d63939", "y", "line", False)
    ds_feed_m = init_dataset("Male Feed (g/bird)", "#f59f00", "y", "line", False)

    # BW Female Chart
    ds_bw_f = init_dataset("Female Bodyweight (g)", "#d63939", "y", "line", False)
    ds_bw_f_std = init_dataset("Std Female BW (g)", "#d63939", "y", "line", False, borderDash=[5,5])
    ds_uni_f = init_dataset("Female Uniformity %", "#206bc4", "y1", "line", False)

    # BW Male Chart
    ds_bw_m = init_dataset("Male Bodyweight (g)", "#f59f00", "y", "line", False)
    ds_bw_m_std = init_dataset("Std Male BW (g)", "#f59f00", "y", "line", False, borderDash=[5,5])
    ds_uni_m = init_dataset("Male Uniformity %", "#206bc4", "y1", "line", False)


    for d in filtered_daily:
        log = d['log']

        # Calculate week and day
        intake_date = flock.intake_date
        diff_time = abs(d['date'] - intake_date).days
        week = (diff_time // 7) + 1
        day = diff_time % 7

        day_str = d['date'].strftime('%d-%m')
        label = f"{week}.{day} ({day_str})"
        labels.append(label)

        # Build Notes for clinical modal trigger
        note_parts = []
        if log.flushing: note_parts.append("[FLUSHING]")
        if log.clinical_notes: note_parts.append(log.clinical_notes)

        # Vacs
        done_vacs = [v.vaccine_name for v in vacs if v.actual_date == log.date]
        if done_vacs: note_parts.append("Vac: " + ", ".join(done_vacs))

        main_photos = [p for p in log.photos if p.note_id is None]

        note_str = " | ".join(note_parts) if note_parts else None
        image_url = url_for('uploaded_file', filename=os.path.basename(main_photos[0].file_path)) if main_photos else None

        def create_point(y_val):
            return {"x": label, "y": y_val, "notes": note_str, "image_url": image_url}

        # Maps
        mort_f = d['mortality_female_pct'] + d['culls_female_pct']
        mort_m = d['mortality_male_pct'] + d['culls_male_pct']

        ds_egg_prod["data"].append(create_point(round(d['egg_prod_pct'], 2)))
        ds_std_egg_prod["data"].append(create_point(round(d.get('std_egg_prod', 0), 2)))
        ds_mort_f["data"].append(create_point(round(mort_f, 2)))
        ds_mort_m["data"].append(create_point(round(mort_m, 2)))
        ds_std_mort_f["data"].append(create_point(round(d.get('std_mortality_female', 0), 3)))

        ds_hatch_egg["data"].append(create_point(round(d['hatch_egg_pct'], 2)))
        ds_std_hatch_egg["data"].append(create_point(round(d.get('std_hatching_egg_pct', 0), 2)))

        water_val = round(d['water_per_bird'], 1) if d['water_per_bird'] >= 0 else None
        water_ratio_val = round(d.get('water_feed_ratio') or 0, 2) if (d.get('water_feed_ratio') or 0) >= 0 else None
        ds_water["data"].append(create_point(water_val))
        ds_water_ratio["data"].append(create_point(water_ratio_val))

        ds_feed_f["data"].append(create_point(round(d['feed_female_gp_bird'], 1)))
        ds_feed_m["data"].append(create_point(round(d['feed_male_gp_bird'], 1)))

        bw_f_val = d['body_weight_female'] if d['body_weight_female'] > 0 else None
        bw_m_val = d['body_weight_male'] if d['body_weight_male'] > 0 else None
        ds_bw_f["data"].append(create_point(bw_f_val))
        ds_bw_m["data"].append(create_point(bw_m_val))
        ds_bw_f_std["data"].append(create_point(log.standard_bw_female if log.standard_bw_female > 0 else None))
        ds_bw_m_std["data"].append(create_point(log.standard_bw_male if log.standard_bw_male > 0 else None))

        uni_f_val = round(d['uniformity_female'] * 100 if d['uniformity_female'] <= 1 else d['uniformity_female'], 2) if d['uniformity_female'] > 0 else None
        uni_m_val = round(d['uniformity_male'] * 100 if d['uniformity_male'] <= 1 else d['uniformity_male'], 2) if d['uniformity_male'] > 0 else None
        ds_uni_f["data"].append(create_point(uni_f_val))
        ds_uni_m["data"].append(create_point(uni_m_val))

    charts['general']['labels'] = labels
    charts['general']['datasets'] = [ds_egg_prod, ds_mort_f, ds_mort_m, ds_std_egg_prod, ds_std_mort_f]

    charts['hatching']['labels'] = labels
    charts['hatching']['datasets'] = [ds_hatch_egg, ds_std_hatch_egg]

    charts['water']['labels'] = labels
    charts['water']['datasets'] = [ds_water, ds_water_ratio]

    charts['feed']['labels'] = labels
    charts['feed']['datasets'] = [ds_feed_f, ds_feed_m]

    charts['bw_male']['labels'] = labels
    charts['bw_male']['datasets'] = [ds_bw_m, ds_bw_m_std, ds_uni_m]

    charts['bw_female']['labels'] = labels
    charts['bw_female']['datasets'] = [ds_bw_f, ds_bw_f_std, ds_uni_f]

    return {"charts": charts}
"""

pattern = re.compile(r'def get_chart_data\(flock_id\):.*?return data\n', re.DOTALL)
new_content = pattern.sub(new_get_chart_data, content)

with open('app.py', 'w') as f:
    f.write(new_content)
