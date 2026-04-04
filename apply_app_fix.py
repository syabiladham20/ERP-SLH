import re

with open('app.py', 'r') as f:
    content = f.read()

new_get_chart_data = """def _generate_chart_payload(flock_id, start_date_str=None, end_date_str=None, mode='daily'):
    flock = Flock.query.get_or_404(flock_id)

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

    # Re-structure for Chart.js unified format
    labels = []

    metrics_map = {
        'egg_prod_pct': [], 'std_egg_prod': [], 'hatch_egg_pct': [], 'std_hatching_egg_pct': [],
        'mortality_f_pct': [], 'mortality_m_pct': [], 'std_mortality_female': [], 'std_mortality_male': [],
        'bw_f': [], 'bw_m': [], 'bw_female_std': [], 'bw_male_std': [],
        'uni_f': [], 'uni_m': [], 'feed_f': [], 'feed_m': [], 'water_per_bird': [], 'water_feed_ratio': []
    }

    dates = []
    notes = []

    if mode == 'weekly' or mode == 'monthly':
        agg_stats = aggregate_weekly_metrics(filtered_daily) if mode == 'weekly' else aggregate_monthly_metrics(filtered_daily)
        label_prefix = "W" if mode == 'weekly' else ""

        for a in agg_stats:
            dates.append(a['date_start'].isoformat())
            lbl = f"{label_prefix}{a['week']}" if mode == 'weekly' else a['month']
            labels.append(lbl)

            mort_f = a['mortality_female_pct'] + a['culls_female_pct']
            mort_m = a['mortality_male_pct'] + a['culls_male_pct']

            metrics_map['mortality_f_pct'].append(round(mort_f, 2))
            metrics_map['mortality_m_pct'].append(round(mort_m, 2))
            metrics_map['egg_prod_pct'].append(round(a['egg_prod_pct'], 2))
            metrics_map['hatch_egg_pct'].append(round(a['hatch_egg_pct'], 2))
            metrics_map['bw_f'].append(round(a['body_weight_female'], 0) if a['body_weight_female'] > 0 else None)
            metrics_map['bw_m'].append(round(a['body_weight_male'], 0) if a['body_weight_male'] > 0 else None)
            metrics_map['uni_f'].append(round(a['uniformity_female'] * 100 if a['uniformity_female'] <= 1 else a['uniformity_female'], 2) if a['uniformity_female'] > 0 else None)
            metrics_map['uni_m'].append(round(a['uniformity_male'] * 100 if a['uniformity_male'] <= 1 else a['uniformity_male'], 2) if a['uniformity_male'] > 0 else None)
            metrics_map['feed_f'].append(round(a['feed_female_gp_bird'], 1))
            metrics_map['feed_m'].append(round(a['feed_male_gp_bird'], 1))
            metrics_map['water_per_bird'].append(round(a['water_per_bird'], 1) if a.get('water_per_bird', 0) >= 0 else None)
            metrics_map['water_feed_ratio'].append(round(a.get('water_feed_ratio'), 2) if a.get('water_feed_ratio') is not None and a.get('water_feed_ratio') >= 0 else None)

            # Missing std for weekly in the current codebase, injecting zeros for now
            metrics_map['std_mortality_female'].append(0)
            metrics_map['std_mortality_male'].append(0)
            metrics_map['std_egg_prod'].append(0)
            metrics_map['std_hatching_egg_pct'].append(0)
            metrics_map['bw_female_std'].append(None)
            metrics_map['bw_male_std'].append(None)
            notes.append(None)

    else:
        for d in filtered_daily:
            log = d['log']
            dates.append(d['date'].isoformat())

            intake_date = flock.intake_date
            diff_time = abs(d['date'] - intake_date).days
            week = (diff_time // 7) + 1
            day = diff_time % 7

            day_str = d['date'].strftime('%d-%m')
            labels.append(f"{week}.{day} ({day_str})")

            mort_f = d['mortality_female_pct'] + d['culls_female_pct']
            mort_m = d['mortality_male_pct'] + d['culls_male_pct']

            metrics_map['mortality_f_pct'].append(round(mort_f, 2))
            metrics_map['mortality_m_pct'].append(round(mort_m, 2))
            metrics_map['egg_prod_pct'].append(round(d['egg_prod_pct'], 2))
            metrics_map['hatch_egg_pct'].append(round(d['hatch_egg_pct'], 2))
            metrics_map['bw_f'].append(d['body_weight_female'] if d['body_weight_female'] > 0 else None)
            metrics_map['bw_m'].append(d['body_weight_male'] if d['body_weight_male'] > 0 else None)
            metrics_map['uni_f'].append(round(d['uniformity_female'] * 100 if d['uniformity_female'] <= 1 else d['uniformity_female'], 2) if d['uniformity_female'] > 0 else None)
            metrics_map['uni_m'].append(round(d['uniformity_male'] * 100 if d['uniformity_male'] <= 1 else d['uniformity_male'], 2) if d['uniformity_male'] > 0 else None)
            metrics_map['feed_f'].append(round(d['feed_female_gp_bird'], 1))
            metrics_map['feed_m'].append(round(d['feed_male_gp_bird'], 1))
            metrics_map['water_per_bird'].append(round(d['water_per_bird'], 1) if d['water_per_bird'] >= 0 else None)
            metrics_map['water_feed_ratio'].append(round(d.get('water_feed_ratio') or 0, 2) if (d.get('water_feed_ratio') or 0) >= 0 else None)

            metrics_map['std_mortality_female'].append(round(d.get('std_mortality_female', 0), 3))
            metrics_map['std_mortality_male'].append(round(d.get('std_mortality_male', 0), 3))
            metrics_map['std_egg_prod'].append(round(d.get('std_egg_prod', 0), 2))
            metrics_map['std_hatching_egg_pct'].append(round(d.get('std_hatching_egg_pct', 0), 2))
            metrics_map['bw_female_std'].append(log.standard_bw_female if log.standard_bw_female > 0 else None)
            metrics_map['bw_male_std'].append(log.standard_bw_male if log.standard_bw_male > 0 else None)

            note_parts = []
            if log.flushing: note_parts.append("[FLUSHING]")
            if log.clinical_notes: note_parts.append(log.clinical_notes)

            done_vacs = [v.vaccine_name for v in vacs if v.actual_date == log.date]
            if done_vacs: note_parts.append("Vac: " + ", ".join(done_vacs))

            main_photos = [p for p in log.photos if p.note_id is None]

            extra_notes = []
            if log.clinical_notes_list:
                for n in log.clinical_notes_list:
                    n_photos = []
                    for p in n.photos:
                        n_photos.append({
                            'url': url_for('uploaded_file', filename=os.path.basename(p.file_path)),
                            'name': p.original_filename or 'Photo'
                        })
                    extra_notes.append({
                        'caption': n.caption,
                        'photos': n_photos
                    })

            has_any_data = (note_parts or main_photos or extra_notes)

            note_obj = None
            if has_any_data:
                main_photo_list = []
                for p in main_photos:
                    main_photo_list.append({
                        'url': url_for('uploaded_file', filename=os.path.basename(p.file_path)),
                        'name': p.original_filename or 'Photo'
                    })

                note_obj = {
                    'main_note': " | ".join(note_parts),
                    'main_photos': main_photo_list,
                    'extra_notes': extra_notes,
                }
            notes.append(note_obj)

    data = {
        'flock_id': flock.flock_id,
        'intake_date': flock.intake_date.isoformat(),
        'labels': labels,
        'dates': dates,
        'notes': notes,
        'metrics': metrics_map
    }

    return data

@app.route('/api/chart_data/<int:flock_id>')
@login_required
@dept_required('Farm')
def get_chart_data(flock_id):
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    mode = request.args.get('mode', 'daily')

    daily_data = _generate_chart_payload(flock_id, start_date_str, end_date_str, 'daily')
    weekly_data = _generate_chart_payload(flock_id, start_date_str, end_date_str, 'weekly')

    return jsonify({
        'daily': daily_data,
        'weekly': weekly_data
    })
"""

pattern = re.compile(r'def get_chart_data\(flock_id\):.*?return data\n', re.DOTALL)
content = pattern.sub(new_get_chart_data, content)

# 1. view_flock
target_modern = "    return render_template('flock_detail_modern.html', flock=flock, logs=list(reversed(enriched_logs)), weekly_data=weekly_data, current_stats=current_stats, global_std=gs, active_flocks=active_flocks, summary_dashboard=summary_dashboard, summary_table=summary_table, health_events=health_events, available_reports=available_reports)"

replacement_modern = """    chart_payload = {'daily': _generate_chart_payload(flock.id, mode='daily'), 'weekly': _generate_chart_payload(flock.id, mode='weekly')}
    return render_template('flock_detail_modern.html', flock=flock, logs=list(reversed(enriched_logs)), weekly_data=weekly_data, current_stats=current_stats, global_std=gs, active_flocks=active_flocks, summary_dashboard=summary_dashboard, summary_table=summary_table, health_events=health_events, available_reports=available_reports, chart_data_daily=chart_payload.get('daily'), chart_data_weekly=chart_payload.get('weekly'))"""

content = content.replace(target_modern, replacement_modern)

# 2. executive_flock_detail
target_readonly = """    return render_template('flock_detail_readonly.html',
                           flock=flock,
                           available_reports=available_reports,
                           logs=list(reversed(enriched_logs)),
                           weekly_data=weekly_data,
                           current_stats=current_stats,
                           global_std=gs,
                           active_flocks=active_flocks,
                           hatch_records=hatch_records,
                           summary_dashboard=summary_dashboard,
                           summary_table=summary_table)"""

replacement_readonly = """    chart_payload = {'daily': _generate_chart_payload(flock.id, mode='daily'), 'weekly': _generate_chart_payload(flock.id, mode='weekly')}
    return render_template('flock_detail_readonly.html',
                           flock=flock,
                           available_reports=available_reports,
                           logs=list(reversed(enriched_logs)),
                           weekly_data=weekly_data,
                           current_stats=current_stats,
                           global_std=gs,
                           active_flocks=active_flocks,
                           hatch_records=hatch_records,
                           summary_dashboard=summary_dashboard,
                           summary_table=summary_table,
                           chart_data_daily=chart_payload.get('daily'),
                           chart_data_weekly=chart_payload.get('weekly'))"""

content = content.replace(target_readonly, replacement_readonly)

with open('app.py', 'w') as f:
    f.write(content)
