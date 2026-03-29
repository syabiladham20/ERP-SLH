import re

with open("app.py", "r") as f:
    content = f.read()

start_marker = "    houses = House.query.order_by(House.name).all()\n\n    active_flocks = Flock.query.filter_by(status='Active').options(joinedload(Flock.house)).all()"
end_marker = "    return render_template('bodyweight.html', houses=houses, active_flocks=active_flocks, grouped_data=grouped_data, today=date.today())"

replacement_code = """    houses = House.query.order_by(House.name).all()

    active_flocks = Flock.query.filter_by(status='Active').options(joinedload(Flock.house)).all()
    active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else ''))

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

        avg_m_diff = "N/A"
        if prev_log and log.body_weight_male is not None and prev_log.body_weight_male is not None:
            diff = log.body_weight_male - prev_log.body_weight_male
            avg_m_diff = f"{'+' if diff >= 0 else ''}{diff:.0f}g"

        avg_f_diff = "N/A"
        if prev_log and log.body_weight_female is not None and prev_log.body_weight_female is not None:
            diff = log.body_weight_female - prev_log.body_weight_female
            avg_f_diff = f"{'+' if diff >= 0 else ''}{diff:.0f}g"

        for i in range(1, 9):
            cur_m = get_p(log, f'M{i}')
            if cur_m and cur_m.body_weight > 0:
                prev_m = get_p(prev_log, f'M{i}')
                diff_g = "N/A"
                diff_u = "N/A"
                if prev_m and prev_m.body_weight > 0:
                    dg = cur_m.body_weight - prev_m.body_weight
                    diff_g = f"{'+' if dg >= 0 else ''}{dg:.0f}g"
                    du = cur_m.uniformity - prev_m.uniformity
                    diff_u = f"{'+' if du >= 0 else ''}{du:.1f}%"

                var_pct = 0
                if log.standard_bw_male and log.standard_bw_male > 0:
                    var_pct = ((cur_m.body_weight - log.standard_bw_male) / log.standard_bw_male) * 100

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
                    diff_g = f"{'+' if dg >= 0 else ''}{dg:.0f}g"
                    du = cur_f.uniformity - prev_f.uniformity
                    diff_u = f"{'+' if du >= 0 else ''}{du:.1f}%"

                var_pct = 0
                if log.standard_bw_female and log.standard_bw_female > 0:
                    var_pct = ((cur_f.body_weight - log.standard_bw_female) / log.standard_bw_female) * 100

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
        if log.body_weight_male and log.standard_bw_male:
            avg_m_var = ((log.body_weight_male - log.standard_bw_male) / log.standard_bw_male) * 100
        avg_f_var = 0
        if log.body_weight_female and log.standard_bw_female:
            avg_f_var = ((log.body_weight_female - log.standard_bw_female) / log.standard_bw_female) * 100

        bodyweight_logs.append({
            'log_id': log.id,
            'house_name': log.flock.house.name,
            'house_id': log.flock.house_id,
            'age_weeks': age_weeks,
            'date': log.date,
            'std_m': log.standard_bw_male or 0,
            'std_f': log.standard_bw_female or 0,
            'avg_m': log.body_weight_male or 0,
            'avg_f': log.body_weight_female or 0,
            'avg_m_diff': avg_m_diff,
            'avg_f_diff': avg_f_diff,
            'avg_m_var': avg_m_var,
            'avg_f_var': avg_f_var,
            'm_parts': m_parts,
            'f_parts': f_parts,
            'has_report': has_report,
            'uni_m': log.uniformity_male or 0,
            'uni_f': log.uniformity_female or 0
        })

    return render_template('bodyweight.html', houses=houses, active_flocks=active_flocks, bodyweight_logs=bodyweight_logs, grouped_data={}, today=date.today())"""

content = content.replace(start_marker, "") # replace the first half to empty
idx = content.find(end_marker)
if idx != -1:
    content = content[:idx] + replacement_code + content[idx + len(end_marker):]
    with open("app.py", "w") as f:
        f.write(content)
    print("Patched!")
else:
    print("Not patched")
