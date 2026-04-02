import re

with open('app.py', 'r') as f:
    content = f.read()

# 1. We need to extract the code from `def flock_detail` that generates `chart_data` and `chart_data_weekly`
start_fd = content.find('def flock_detail(id):')
start_enrich = content.find('daily_stats = enrich_flock_data', start_fd)
start_cdw = content.find('chart_data_weekly = {', start_fd)
end_cdw = content.find('    # 5. Current Stats', start_cdw)

# The logic includes:
# daily_stats = enrich_flock_data(flock, logs, hatch_records)
# weekly_stats = aggregate_weekly_metrics(daily_stats)
# weekly_data = [] (for table)
# chart_data = { ... }
# chart_data_weekly = { ... }

# We can create a helper function `def build_chart_payload(flock_id):`
# But wait, it needs `flock`, `logs`, `hatch_records`.

api_target = "@app.route('/api/chart_data/<int:flock_id>')"
api_start = content.find(api_target)
api_end = content.find("@app.route", api_start + 10)

new_api = """@app.route('/api/chart_data/<int:flock_id>')
@login_required
def get_chart_data(flock_id):
    flock = Flock.query.get_or_404(flock_id)

    # Note: Using get_flock_dashboard_payload to ensure DRY principle.
    payload = get_flock_dashboard_payload(flock)
    return jsonify(payload)

def get_flock_dashboard_payload(flock):
    logs = DailyLog.query.options(joinedload(DailyLog.partition_weights), joinedload(DailyLog.photos), joinedload(DailyLog.clinical_notes_list)).filter_by(flock_id=flock.id).order_by(DailyLog.date.asc()).all()
    hatch_records = Hatchability.query.filter_by(flock_id=flock.id).order_by(Hatchability.setting_date.desc()).all()

    from metrics import enrich_flock_data, aggregate_weekly_metrics
    daily_stats = enrich_flock_data(flock, logs, hatch_records)
    weekly_stats = aggregate_weekly_metrics(daily_stats)

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
        'water_per_bird': [round(d['water_per_bird'], 1) if d['water_per_bird'] >= 0 else None for d in daily_stats],
        'water_feed_ratio': [round(d.get('water_feed_ratio'), 2) if d.get('water_feed_ratio') is not None and d.get('water_feed_ratio') >= 0 else None for d in daily_stats],
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
        pw_map = {pw.partition_name: pw for pw in log.partition_weights}
        for i in range(1, 9):
            chart_data[f'bw_M{i}'].append(pw_map.get(f'M{i}').body_weight if f'M{i}' in pw_map else None)
            chart_data[f'bw_F{i}'].append(pw_map.get(f'F{i}').body_weight if f'F{i}' in pw_map else None)

        # Build combined note/image payload
        note_parts = []
        if log.clinical_notes:
            note_parts.append(log.clinical_notes)
        for note in log.clinical_notes_list:
            if note.caption:
                note_parts.append(note.caption)

        note_text = ', '.join(note_parts) if note_parts else None

        image_url = None
        if log.photos:
            # Try to find a photo with category 'Clinical'
            for photo in log.photos:
                if photo.category == 'Clinical':
                    image_url = photo.url
                    break
            if not image_url:
                 image_url = log.photos[0].url

        chart_data['notes'].append(note_text)
        # Adding image_url directly into chart_data so it matches index-wise for daily points.
        # However, for chart point data, the frontend usually expects arrays of objects if we use {x,y,note}.
        # Wait, the current frontend relies on `chart_data.notes` etc being arrays aligned with dates.
        # Actually in app.py's flock_detail, `notes` was built as a list of dicts:
        # {'date': ..., 'note': ..., 'main_note': ..., 'photos': ...}

        # Let's see the exact original chart_data construction:
        if note_text or image_url:
            chart_data['notes'].append({
                'date': log.date.strftime('%Y-%m-%d'),
                'note': note_text,
                'photos': [{'url': image_url}] if image_url else []
            })
        else:
            chart_data['notes'].append(None)

        chart_data['medication_active'].append(d.get('medication_active', False))
        chart_data['medication_names'].append(d.get('medication_names', []))

    chart_data_weekly = {
        'weeks': [str(w['week']) for w in weekly_stats],
        'mortality_cum_male': [round(w['mortality_cum_male_pct'], 2) for w in weekly_stats],
        'mortality_cum_female': [round(w['mortality_cum_female_pct'], 2) for w in weekly_stats],
        'mortality_daily_male': [round(w['mortality_male_pct'], 2) for w in weekly_stats],
        'mortality_daily_female': [round(w['mortality_female_pct'], 2) for w in weekly_stats],
        'std_mortality_male': [round(w['std_mortality_male'], 3) for w in weekly_stats],
        'std_mortality_female': [round(w['std_mortality_female'], 3) for w in weekly_stats],
        'culls_daily_male': [round(w['culls_male_pct'], 2) for w in weekly_stats],
        'culls_daily_female': [round(w['culls_female_pct'], 2) for w in weekly_stats],
        'egg_prod': [round(w['egg_prod_pct'], 2) for w in weekly_stats],
        'std_egg_prod': [round(w['std_egg_prod'], 2) for w in weekly_stats],
        'hatch_egg_pct': [round(w['hatch_egg_pct'], 2) for w in weekly_stats],
        'std_hatching_egg_pct': [round(w['std_hatching_egg_pct'], 2) for w in weekly_stats],
        'cull_eggs_jumbo_pct': [round(w['cull_eggs_jumbo_pct'], 2) for w in weekly_stats],
        'cull_eggs_small_pct': [round(w['cull_eggs_small_pct'], 2) for w in weekly_stats],
        'cull_eggs_crack_pct': [round(w['cull_eggs_crack_pct'], 2) for w in weekly_stats],
        'cull_eggs_abnormal_pct': [round(w['cull_eggs_abnormal_pct'], 2) for w in weekly_stats],
        'male_ratio': [round(w['male_ratio_stock'], 2) for w in weekly_stats],
        'bw_male_std': [w['std_bw_male'] for w in weekly_stats],
        'bw_female_std': [w['std_bw_female'] for w in weekly_stats],
        'unif_male': [w['uniformity_male'] for w in weekly_stats],
        'unif_female': [w['uniformity_female'] for w in weekly_stats],
        'bw_f': [w['body_weight_female'] for w in weekly_stats],
        'bw_m': [w['body_weight_male'] for w in weekly_stats],
        'water_per_bird': [round(w['water_per_bird'], 1) for w in weekly_stats],
        'water_feed_ratio': [round(w['water_feed_ratio'], 2) for w in weekly_stats],
        'feed_male_gp_bird': [round(w['feed_male_gp_bird'], 1) for w in weekly_stats],
        'feed_female_gp_bird': [round(w['feed_female_gp_bird'], 1) for w in weekly_stats]
    }

    for i in range(1, 9):
        chart_data_weekly[f'bw_M{i}'] = [w.get(f'bw_M{i}', 0) for w in weekly_stats]
        chart_data_weekly[f'bw_F{i}'] = [w.get(f'bw_F{i}', 0) for w in weekly_stats]

    return {
        'daily': chart_data,
        'weekly': chart_data_weekly
    }
"""

content = content[:api_start] + new_api + "\n" + content[api_end:]

with open('app.py', 'w') as f:
    f.write(content)
