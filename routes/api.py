from flask import Blueprint, jsonify, request, url_for
from flask_login import login_required
from sqlalchemy.orm import joinedload
from datetime import datetime
import os

# Import extensions and models from the main app/extensions
from extensions import db
from app import Flock, DailyLog, Hatchability, Medication, Vaccine, Standard, GlobalStandard, \
                enrich_flock_data, aggregate_weekly_metrics, dept_required

api_bp = Blueprint('api', __name__)

@api_bp.route('/chart_data/<int:flock_id>')
@login_required
@dept_required('Farm')
def get_chart_data(flock_id):
    flock = Flock.query.get_or_404(flock_id)

    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    mode = request.args.get('mode', 'daily')

    hatch_records = Hatchability.query.filter_by(flock_id=flock_id).all()
    all_logs = DailyLog.query.options(joinedload(DailyLog.photos), joinedload(DailyLog.clinical_notes_list)).filter_by(flock_id=flock_id).order_by(DailyLog.date.asc()).all()

    meds = Medication.query.filter_by(flock_id=flock_id).all()
    vacs = Vaccine.query.filter_by(flock_id=flock_id).filter(Vaccine.actual_date != None).all()

    daily_stats = enrich_flock_data(flock, all_logs, hatch_records)

    filtered_daily = []
    for d in daily_stats:
        if start_date_str and d['date'] < datetime.strptime(start_date_str, '%Y-%m-%d').date(): continue
        if end_date_str and d['date'] > datetime.strptime(end_date_str, '%Y-%m-%d').date(): continue
        filtered_daily.append(d)

    labels = []
    charts = {
        'generalChart': {'labels': [], 'datasets': []},
        'hatchingEggChart': {'labels': [], 'datasets': []},
        'waterChart': {'labels': [], 'datasets': []},
        'feedChart': {'labels': [], 'datasets': []},
        'maleChart': {'labels': [], 'datasets': []},
        'femaleChart': {'labels': [], 'datasets': []}
    }

    def init_dataset(label, color, yAxisID, type_='line', fill=False, tension=0.1, borderDash=None, hidden=False, stack=None, is_bar=False, datalabels=None):
        if type_ == 'line' and datalabels is None:
            datalabels = {"display": False}

        ds = {
            "label": label, "data": [], "borderColor": color,
            "backgroundColor": color if is_bar else color + "33",
            "yAxisID": yAxisID, "tension": tension, "hidden": hidden, "type": type_
        }
        if fill: ds["fill"] = True
        if borderDash: ds["borderDash"] = borderDash
        if stack: ds["stack"] = stack
        if datalabels is not None: ds["datalabels"] = datalabels
        return ds

    # General Chart
    ds_egg_prod = init_dataset("Egg Prod %", "#206bc4", "y", "line", False)
    ds_std_egg_prod = init_dataset("Std Egg Prod %", "#888888", "y", "line", False, borderDash=[5,5], hidden=True)
    ds_mort_f = init_dataset("Fem Depletion %", "#d63939", "y1", "bar", True, is_bar=True)
    ds_mort_m = init_dataset("Male Depletion %", "#f59f00", "y1", "bar", True, is_bar=True)
    ds_std_mort_f = init_dataset("Std Fem Depletion %", "#888888", "y1", "line", False, borderDash=[5,5], hidden=True)

    # Hatching Chart
    ds_hatch_egg = init_dataset("Hatching Egg %", "#2fb344", "y", "line", False)
    ds_std_hatch_egg = init_dataset("Std Hatching Egg %", "#888888", "y", "line", False, borderDash=[5,5], hidden=True)

    # Culls datasets (stacked bars for hatching chart)
    ds_jumbo = init_dataset("Jumbo %", "#d63939", "y", "bar", True, is_bar=True, stack="culls")
    ds_small = init_dataset("Small %", "#f59f00", "y", "bar", True, is_bar=True, stack="culls")
    ds_crack = init_dataset("Crack %", "#1d2a3a", "y", "bar", True, is_bar=True, stack="culls")
    ds_abnormal = init_dataset("Abnormal %", "#ae3ec9", "y", "bar", True, is_bar=True, stack="culls")

    # Water Chart
    ds_water = init_dataset("Water Intake (ml/bird)", "#4299e1", "y", "line", True)
    ds_water_ratio = init_dataset("Water:Feed Ratio", "#6574cd", "y1", "line", False)

    # Feed Chart
    ds_feed_f = init_dataset("Female Feed (g/bird)", "#d63939", "y", "line", False)
    ds_feed_m = init_dataset("Male Feed (g/bird)", "#f59f00", "y", "line", False)

    # BW Female Chart
    ds_bw_f = init_dataset("Female Bodyweight (g)", "#d63939", "y", "line", False)
    ds_bw_f_std = init_dataset("Std Female BW (g)", "#888888", "y", "line", False, borderDash=[5,5])
    ds_uni_f = init_dataset("Female Uniformity %", "#206bc4", "y1", "line", False)

    # BW Male Chart
    ds_bw_m = init_dataset("Male Bodyweight (g)", "#f59f00", "y", "line", False)
    ds_bw_m_std = init_dataset("Std Male BW (g)", "#888888", "y", "line", False, borderDash=[5,5])
    ds_uni_m = init_dataset("Male Uniformity %", "#206bc4", "y1", "line", False)

    for d in filtered_daily:
        log = d['log']

        # --- THE FIX: Unique Label for spacing + Date for readability ---
        label = f"{log.age_week_format}"
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
        mort_f = (d.get('mortality_female_pct') or 0.0) + (d.get('culls_female_pct') or 0.0)
        mort_m = (d.get('mortality_male_pct') or 0.0) + (d.get('culls_male_pct') or 0.0)

        # Query editable Standard table by SSOT age_week
        std_record = Standard.query.filter_by(week=log.age_week).first()

        ds_egg_prod["data"].append(create_point(round(d.get('egg_prod_pct') or 0.0, 2)))
        ds_mort_f["data"].append(create_point(round(mort_f, 2)))
        ds_mort_m["data"].append(create_point(round(mort_m, 2)))

        ds_hatch_egg["data"].append(create_point(round(d.get('hatch_egg_pct') or 0.0, 2)))
        ds_jumbo["data"].append(create_point(round(d.get('cull_eggs_jumbo_pct') or 0.0, 2) if (d.get('cull_eggs_jumbo_pct') or 0.0) > 0 else None))
        ds_small["data"].append(create_point(round(d.get('cull_eggs_small_pct') or 0.0, 2) if (d.get('cull_eggs_small_pct') or 0.0) > 0 else None))
        ds_crack["data"].append(create_point(round(d.get('cull_eggs_crack_pct') or 0.0, 2) if (d.get('cull_eggs_crack_pct') or 0.0) > 0 else None))
        ds_abnormal["data"].append(create_point(round(d.get('cull_eggs_abnormal_pct') or 0.0, 2) if (d.get('cull_eggs_abnormal_pct') or 0.0) > 0 else None))

        water_val = round(d.get('water_per_bird', 0.0), 1) if d.get('water_per_bird') is not None and d.get('water_per_bird') >= 0 else None
        water_ratio_val = round(d.get('water_feed_ratio', 0.0), 2) if d.get('water_feed_ratio') is not None and d.get('water_feed_ratio') >= 0 else None

        ds_water["data"].append(create_point(water_val))
        ds_water_ratio["data"].append(create_point(water_ratio_val))

        ds_feed_f["data"].append(create_point(round(d.get('feed_female_gp_bird') or 0.0, 1)))
        ds_feed_m["data"].append(create_point(round(d.get('feed_male_gp_bird') or 0.0, 1)))

        bw_f_val = d.get('body_weight_female') if d.get('body_weight_female') is not None and d.get('body_weight_female') > 0 else None
        bw_m_val = d.get('body_weight_male') if d.get('body_weight_male') is not None and d.get('body_weight_male') > 0 else None
        ds_bw_f["data"].append(create_point(bw_f_val))
        ds_bw_m["data"].append(create_point(bw_m_val))

        # Handle 'Day 0' Gap for Standards
        if log.age_days_total <= 0:
            ds_std_egg_prod["data"].append(create_point(None))
            ds_std_mort_f["data"].append(create_point(None))
            ds_std_hatch_egg["data"].append(create_point(None))
            ds_bw_f_std["data"].append(create_point(None))
            ds_bw_m_std["data"].append(create_point(None))
        else:
            std_egg = std_record.std_egg_prod if std_record and std_record.std_egg_prod is not None else None
            std_mort_f = std_record.std_mortality_female if std_record and std_record.std_mortality_female is not None else None
            std_hatch = std_record.std_hatching_egg_pct if std_record and std_record.std_hatching_egg_pct is not None else None
            std_bw_f = std_record.std_bw_female if std_record and std_record.std_bw_female is not None else None
            std_bw_m = std_record.std_bw_male if std_record and std_record.std_bw_male is not None else None

            ds_std_egg_prod["data"].append(create_point(round(std_egg, 2) if std_egg is not None else None))
            ds_std_mort_f["data"].append(create_point(round(std_mort_f, 3) if std_mort_f is not None else None))
            ds_std_hatch_egg["data"].append(create_point(round(std_hatch, 2) if std_hatch is not None else None))
            ds_bw_f_std["data"].append(create_point(std_bw_f))
            ds_bw_m_std["data"].append(create_point(std_bw_m))

        uni_f_val = round(d['uniformity_female'] * 100 if d['uniformity_female'] <= 1 else d['uniformity_female'], 2) if d.get('uniformity_female') is not None and d['uniformity_female'] > 0 else None
        uni_m_val = round(d['uniformity_male'] * 100 if d['uniformity_male'] <= 1 else d['uniformity_male'], 2) if d.get('uniformity_male') is not None and d['uniformity_male'] > 0 else None
        ds_uni_f["data"].append(create_point(uni_f_val))
        ds_uni_m["data"].append(create_point(uni_m_val))

    charts['generalChart']['labels'] = labels
    charts['generalChart']['datasets'] = [ds_egg_prod, ds_mort_f, ds_mort_m, ds_std_egg_prod, ds_std_mort_f]

    charts['hatchingEggChart']['labels'] = labels
    charts['hatchingEggChart']['datasets'] = [ds_hatch_egg, ds_std_hatch_egg, ds_jumbo, ds_small, ds_crack, ds_abnormal]

    charts['waterChart']['labels'] = labels
    charts['waterChart']['datasets'] = [ds_water, ds_water_ratio]

    charts['feedChart']['labels'] = labels
    charts['feedChart']['datasets'] = [ds_feed_f, ds_feed_m]

    charts['maleChart']['labels'] = labels
    charts['maleChart']['datasets'] = [ds_bw_m, ds_bw_m_std, ds_uni_m]

    charts['femaleChart']['labels'] = labels
    charts['femaleChart']['datasets'] = [ds_bw_f, ds_bw_f_std, ds_uni_f]

    # Weekly Aggregation
    weekly_stats = aggregate_weekly_metrics(daily_stats)
    filtered_weekly = []
    for w in weekly_stats:
        filtered_weekly.append(w)

    weekly_charts = {
        'generalChart': {'labels': [], 'datasets': []},
        'hatchingEggChart': {'labels': [], 'datasets': []},
        'waterChart': {'labels': [], 'datasets': []},
        'feedChart': {'labels': [], 'datasets': []},
        'maleChart': {'labels': [], 'datasets': []},
        'femaleChart': {'labels': [], 'datasets': []}
    }

    # Clone Datasets for weekly
    ds_egg_prod_w = init_dataset("Egg Prod %", "#206bc4", "y", "line", False)
    ds_std_egg_prod_w = init_dataset("Std Egg Prod %", "#888888", "y", "line", False, borderDash=[5,5], hidden=True)
    ds_mort_f_w = init_dataset("Fem Depletion %", "#d63939", "y1", "bar", True, is_bar=True)
    ds_mort_m_w = init_dataset("Male Depletion %", "#f59f00", "y1", "bar", True, is_bar=True)
    ds_std_mort_f_w = init_dataset("Std Fem Depletion %", "#888888", "y1", "line", False, borderDash=[5,5], hidden=True)

    ds_hatch_egg_w = init_dataset("Hatching Egg %", "#2fb344", "y", "line", False)
    ds_std_hatch_egg_w = init_dataset("Std Hatching Egg %", "#888888", "y", "line", False, borderDash=[5,5], hidden=True)

    ds_jumbo_w = init_dataset("Jumbo %", "#d63939", "y", "bar", True, is_bar=True, stack="culls")
    ds_small_w = init_dataset("Small %", "#f59f00", "y", "bar", True, is_bar=True, stack="culls")
    ds_crack_w = init_dataset("Crack %", "#1d2a3a", "y", "bar", True, is_bar=True, stack="culls")
    ds_abnormal_w = init_dataset("Abnormal %", "#ae3ec9", "y", "bar", True, is_bar=True, stack="culls")

    ds_water_w = init_dataset("Water Intake (ml/bird)", "#4299e1", "y", "line", True)
    ds_water_ratio_w = init_dataset("Water:Feed Ratio", "#6574cd", "y1", "line", False)

    ds_feed_f_w = init_dataset("Female Feed (g/bird)", "#d63939", "y", "line", False)
    ds_feed_m_w = init_dataset("Male Feed (g/bird)", "#f59f00", "y", "line", False)

    ds_bw_f_w = init_dataset("Female Bodyweight (g)", "#d63939", "y", "line", False)
    ds_bw_f_std_w = init_dataset("Std Female BW (g)", "#888888", "y", "line", False, borderDash=[5,5])
    ds_uni_f_w = init_dataset("Female Uniformity %", "#206bc4", "y1", "line", False)

    ds_bw_m_w = init_dataset("Male Bodyweight (g)", "#f59f00", "y", "line", False)
    ds_bw_m_std_w = init_dataset("Std Male BW (g)", "#888888", "y", "line", False, borderDash=[5,5])
    ds_uni_m_w = init_dataset("Male Uniformity %", "#206bc4", "y1", "line", False)

    weekly_labels = []

    for w in filtered_weekly:
        label = f"Week {w['week']}"
        weekly_labels.append(label)

        def create_point_w(y_val):
            return {"x": label, "y": y_val}

        std_record = Standard.query.filter_by(week=w['week']).first()

        # Maps
        mort_f = (w.get('mortality_female_pct') or 0.0) * 100 + (w.get('culls_female_pct') or 0.0) * 100 if w.get('mortality_female_pct') is not None else 0.0
        mort_m = (w.get('mortality_male_pct') or 0.0) * 100 + (w.get('culls_male_pct') or 0.0) * 100 if w.get('mortality_male_pct') is not None else 0.0

        ds_egg_prod_w["data"].append(create_point_w(round(w.get('egg_prod_pct') or 0.0, 2)))
        ds_mort_f_w["data"].append(create_point_w(round(mort_f, 2)))
        ds_mort_m_w["data"].append(create_point_w(round(mort_m, 2)))

        ds_hatch_egg_w["data"].append(create_point_w(round(w.get('hatch_egg_pct') or 0.0, 2)))
        ds_jumbo_w["data"].append(create_point_w(round(w.get('cull_eggs_jumbo_pct') or 0.0, 2) * 100 if (w.get('cull_eggs_jumbo_pct') or 0.0) > 0 else None))
        ds_small_w["data"].append(create_point_w(round(w.get('cull_eggs_small_pct') or 0.0, 2) * 100 if (w.get('cull_eggs_small_pct') or 0.0) > 0 else None))
        ds_crack_w["data"].append(create_point_w(round(w.get('cull_eggs_crack_pct') or 0.0, 2) * 100 if (w.get('cull_eggs_crack_pct') or 0.0) > 0 else None))
        ds_abnormal_w["data"].append(create_point_w(round(w.get('cull_eggs_abnormal_pct') or 0.0, 2) * 100 if (w.get('cull_eggs_abnormal_pct') or 0.0) > 0 else None))

        water_val = round(w.get('water_per_bird', 0.0), 1) if w.get('water_per_bird') is not None and w.get('water_per_bird') >= 0 else None
        ds_water_w["data"].append(create_point_w(water_val))
        ds_water_ratio_w["data"].append(create_point_w(None)) # Omitted for weekly unless calculated

        ds_feed_f_w["data"].append(create_point_w(round(w.get('feed_female_gp_bird') or 0.0, 1)))
        ds_feed_m_w["data"].append(create_point_w(round(w.get('feed_male_gp_bird') or 0.0, 1)))

        bw_f_val = w.get('body_weight_female') if w.get('body_weight_female') is not None and w.get('body_weight_female') > 0 else None
        bw_m_val = w.get('body_weight_male') if w.get('body_weight_male') is not None and w.get('body_weight_male') > 0 else None
        ds_bw_f_w["data"].append(create_point_w(bw_f_val))
        ds_bw_m_w["data"].append(create_point_w(bw_m_val))

        if w['week'] <= 0:
            ds_std_egg_prod_w["data"].append(create_point_w(None))
            ds_std_mort_f_w["data"].append(create_point_w(None))
            ds_std_hatch_egg_w["data"].append(create_point_w(None))
            ds_bw_f_std_w["data"].append(create_point_w(None))
            ds_bw_m_std_w["data"].append(create_point_w(None))
        else:
            std_egg = std_record.std_egg_prod if std_record and std_record.std_egg_prod is not None else None
            std_mort_f = std_record.std_mortality_female if std_record and std_record.std_mortality_female is not None else None
            std_hatch = std_record.std_hatching_egg_pct if std_record and std_record.std_hatching_egg_pct is not None else None
            std_bw_f = std_record.std_bw_female if std_record and std_record.std_bw_female is not None else None
            std_bw_m = std_record.std_bw_male if std_record and std_record.std_bw_male is not None else None

            ds_std_egg_prod_w["data"].append(create_point_w(round(std_egg, 2) if std_egg is not None else None))
            ds_std_mort_f_w["data"].append(create_point_w(round(std_mort_f, 3) if std_mort_f is not None else None))
            ds_std_hatch_egg_w["data"].append(create_point_w(round(std_hatch, 2) if std_hatch is not None else None))
            ds_bw_f_std_w["data"].append(create_point_w(std_bw_f))
            ds_bw_m_std_w["data"].append(create_point_w(std_bw_m))

        uni_f_val = round(w['uniformity_female'] * 100 if w['uniformity_female'] <= 1 else w['uniformity_female'], 2) if w.get('uniformity_female') is not None and w['uniformity_female'] > 0 else None
        uni_m_val = round(w['uniformity_male'] * 100 if w['uniformity_male'] <= 1 else w['uniformity_male'], 2) if w.get('uniformity_male') is not None and w['uniformity_male'] > 0 else None
        ds_uni_f_w["data"].append(create_point_w(uni_f_val))
        ds_uni_m_w["data"].append(create_point_w(uni_m_val))

    weekly_charts['generalChart']['labels'] = weekly_labels
    weekly_charts['generalChart']['datasets'] = [ds_egg_prod_w, ds_mort_f_w, ds_mort_m_w, ds_std_egg_prod_w, ds_std_mort_f_w]

    weekly_charts['hatchingEggChart']['labels'] = weekly_labels
    weekly_charts['hatchingEggChart']['datasets'] = [ds_hatch_egg_w, ds_std_hatch_egg_w, ds_jumbo_w, ds_small_w, ds_crack_w, ds_abnormal_w]

    weekly_charts['waterChart']['labels'] = weekly_labels
    weekly_charts['waterChart']['datasets'] = [ds_water_w, ds_water_ratio_w]

    weekly_charts['feedChart']['labels'] = weekly_labels
    weekly_charts['feedChart']['datasets'] = [ds_feed_f_w, ds_feed_m_w]

    weekly_charts['maleChart']['labels'] = weekly_labels
    weekly_charts['maleChart']['datasets'] = [ds_bw_m_w, ds_bw_m_std_w, ds_uni_m_w]

    weekly_charts['femaleChart']['labels'] = weekly_labels
    weekly_charts['femaleChart']['datasets'] = [ds_bw_f_w, ds_bw_f_std_w, ds_uni_f_w]

    if mode == 'daily':
        return jsonify({"daily": charts})
    elif mode == 'weekly':
        return jsonify({"weekly": weekly_charts})

    return jsonify({"daily": charts, "weekly": weekly_charts})
