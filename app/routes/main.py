from app.handlers import APP_VERSION
from metrics import calculate_metrics, enrich_flock_data, aggregate_weekly_metrics, aggregate_monthly_metrics, METRICS_REGISTRY
from flask import render_template, request, redirect, flash, url_for, session, send_from_directory
from flask_login import login_required, current_user
from app.database import db
from app.models.models import *
from sqlalchemy.orm import joinedload
import os
from datetime import datetime, date, timedelta

def register_main_routes(app):

    from app.constants import (
        REARING_PHASES,
    )
    from app.utils import dept_required, natural_sort_key

    @app.route('/')
    @login_required
    @dept_required('Farm')
    def index():
        active_flocks = Flock.query.options(joinedload(Flock.logs).joinedload(DailyLog.partition_weights), joinedload(Flock.logs).joinedload(DailyLog.photos), joinedload(Flock.logs).joinedload(DailyLog.clinical_notes_list), joinedload(Flock.house)).filter_by(status='Active').all()

        # Inventory Check for Dashboard
        low_stock_items = InventoryItem.query.filter(InventoryItem.current_stock < InventoryItem.min_stock_level).all()
        low_stock_count = len(low_stock_items)
        normal_stock_items = InventoryItem.query.filter(InventoryItem.current_stock >= InventoryItem.min_stock_level).all()


        if active_flocks:
                active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else ''))

        today = date.today()
        yesterday = today - timedelta(days=1)

        for f in active_flocks:
            daily_stats = enrich_flock_data(f, f.logs)

            f.rearing_mort_m_pct = 0
            f.rearing_mort_f_pct = 0
            f.prod_mort_m_pct = 0
            f.prod_mort_f_pct = 0
            f.male_ratio_pct = 0
            f.has_log_today = False

            # Age
            days_age = (today - f.intake_date).days
            f.age_weeks = 0 if days_age == 0 else ((days_age - 1) // 7) + 1 if days_age > 0 else 0
            f.age_days = ((days_age - 1) % 7) + 1 if days_age > 0 else 0
            f.current_week = 0 if days_age == 0 else ((days_age - 1) // 7) + 1 if days_age > 0 else 0

            # Stats
            if daily_stats:
                last = daily_stats[-1]
                if last['date'] == today and last.get('is_daily_entry_submitted', False):
                    f.has_log_today = True

                # Cumulative Pct (Phase specific)
                if getattr(f, 'calculated_phase', f.phase) in REARING_PHASES:
                    f.rearing_mort_m_pct = last['mortality_cum_male_pct']
                    f.rearing_mort_f_pct = last['mortality_cum_female_pct']
                else:
                    f.prod_mort_m_pct = last['mortality_cum_male_pct']
                    f.prod_mort_f_pct = last['mortality_cum_female_pct']

                if last['male_ratio_stock']:
                    f.male_ratio_pct = last['male_ratio_stock']

            # Daily Stats & Trends
            f.daily_stats = {
                'mort_m_pct': 0, 'mort_f_pct': 0, 'egg_pct': 0,
                'mort_m_trend': 'flat', 'mort_f_trend': 'flat', 'egg_trend': 'flat',
                'mort_m_diff': 0, 'mort_f_diff': 0, 'egg_diff': 0,
                'has_today': False,
                'show_data': False,
                'data_date': None
            }

            # Map date -> stat
            stats_map = { d['date']: d for d in daily_stats }
            stats_today = stats_map.get(today)

            # Determine Display Data (Today or Latest)
            display_data = None
            if stats_today and stats_today.get('is_daily_entry_submitted', False):
                f.daily_stats['has_today'] = True
                display_data = stats_today
            elif daily_stats:
                display_data = daily_stats[-1]

            if display_data:
                f.daily_stats['show_data'] = True
                f.daily_stats['data_date'] = display_data['date']

                f.daily_stats['mort_m_pct'] = display_data['mortality_male_pct']
                f.daily_stats['mort_f_pct'] = display_data['mortality_female_pct']
                f.daily_stats['egg_pct'] = display_data['egg_prod_pct']

                # Trend Calculation (vs Previous Day of DATA DATE)
                # Use previous AVAILABLE record if strict yesterday is missing?
                # Or use list index
                stats_prev = None
                if display_data in daily_stats:
                    idx = daily_stats.index(display_data)
                    if idx > 0:
                        stats_prev = daily_stats[idx-1]
                else:
                     # Fallback
                     prev_date = display_data['date'] - timedelta(days=1)
                     stats_prev = stats_map.get(prev_date)

                if stats_prev:
                    f.daily_stats['mort_m_diff'] = display_data['mortality_male_pct'] - stats_prev['mortality_male_pct']
                    f.daily_stats['mort_f_diff'] = display_data['mortality_female_pct'] - stats_prev['mortality_female_pct']
                    f.daily_stats['egg_diff'] = display_data['egg_prod_pct'] - stats_prev['egg_prod_pct']

                    if round(f.daily_stats['mort_m_diff'], 2) > 0: f.daily_stats['mort_m_trend'] = 'up'
                    elif round(f.daily_stats['mort_m_diff'], 2) < 0: f.daily_stats['mort_m_trend'] = 'down'

                    if round(f.daily_stats['mort_f_diff'], 2) > 0: f.daily_stats['mort_f_trend'] = 'up'
                    elif round(f.daily_stats['mort_f_diff'], 2) < 0: f.daily_stats['mort_f_trend'] = 'down'

                    if round(f.daily_stats['egg_diff'], 2) > 0: f.daily_stats['egg_trend'] = 'up'
                    elif round(f.daily_stats['egg_diff'], 2) < 0: f.daily_stats['egg_trend'] = 'down'

        # Determine the date range for "This Week" (Monday to Sunday)
        weekday = today.weekday() # Monday is 0 and Sunday is 6
        this_week_start = today - timedelta(days=weekday)
        this_week_end = this_week_start + timedelta(days=6)

        # Determine the date range for "Next Week" (Monday to Sunday)
        next_week_start = this_week_end + timedelta(days=1)
        next_week_end = next_week_start + timedelta(days=6)

        active_flock_ids = [f.id for f in active_flocks]

        # Query uncompleted vaccines for these active flocks
        if active_flock_ids:
            uncompleted_vaccines = Vaccine.query.options(joinedload(Vaccine.flock).joinedload(Flock.house)).filter(
                Vaccine.flock_id.in_(active_flock_ids),
                Vaccine.est_date >= this_week_start,
                Vaccine.est_date <= next_week_end,
                Vaccine.actual_date.is_(None)
            ).order_by(Vaccine.est_date).all()
        else:
            uncompleted_vaccines = []

        this_week_vaccines = []
        next_week_vaccines = []

        for v in uncompleted_vaccines:
            if this_week_start <= v.est_date <= this_week_end:
                this_week_vaccines.append(v)
            elif next_week_start <= v.est_date <= next_week_end:
                next_week_vaccines.append(v)

        return render_template('index_modern.html',
                               active_flocks=active_flocks,
                               today=today,
                               low_stock_items=low_stock_items,
                               low_stock_count=low_stock_count,
                               normal_stock_items=normal_stock_items,
                               this_week_vaccines=this_week_vaccines,
                               next_week_vaccines=next_week_vaccines)

    @app.route('/offline_mirror')
    def offline_mirror():
        return render_template('offline_mirror.html')

    @app.route('/offline')
    def offline():
        return render_template('offline.html')

    @app.route('/sw.js')
    def serve_sw():
        # Return as a Jinja template to inject the dynamic CACHE_NAME version
        response = app.make_response(render_template('sw.js', version=APP_VERSION))
        response.headers['Content-Type'] = 'application/javascript'
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response

    @app.route('/uploads/<filename>')
    def uploaded_file(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
