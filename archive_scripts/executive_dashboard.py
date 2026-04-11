@app.route('/executive_dashboard')
def executive_dashboard():
    # Role Check: Admin or Management
    if not session.get('is_admin') and session.get('user_role') != 'Management':
        flash("Access Denied: Executive View Only.", "danger")
        return redirect(url_for('index'))

    # --- Farm Data ---
    active_flocks = Flock.query.options(joinedload(Flock.logs).joinedload(DailyLog.partition_weights), joinedload(Flock.logs).joinedload(DailyLog.photos), joinedload(Flock.logs).joinedload(DailyLog.clinical_notes_list), joinedload(Flock.house)).filter_by(status='Active').all()
    active_flocks.sort(key=lambda x: natural_sort_key(x.house.name if x.house else ''))

    today = date.today()

    # Inventory Check
    low_stock_items = InventoryItem.query.filter(InventoryItem.current_stock < InventoryItem.min_stock_level).all()
    low_stock_count = len(low_stock_items)
    normal_stock_items = InventoryItem.query.filter(InventoryItem.current_stock >= InventoryItem.min_stock_level).all()

    # Pre-fetch Hatchability Data (Optimization: Bulk Fetch)
    flock_ids = [f.id for f in active_flocks]
    all_hatch_records = Hatchability.query.filter(Hatchability.flock_id.in_(flock_ids)).order_by(Hatchability.setting_date.desc()).all()

    flock_hatch_map = {}
    for h in all_hatch_records:
        if h.flock_id not in flock_hatch_map:
            flock_hatch_map[h.flock_id] = {
                'latest': h,  # First record is latest due to ordering
                'hatched_sum': 0,
                'set_sum': 0,
                'records': []
            }
        flock_hatch_map[h.flock_id]['hatched_sum'] += (h.hatched_chicks or 0)
        flock_hatch_map[h.flock_id]['set_sum'] += (h.egg_set or 0)
        flock_hatch_map[h.flock_id]['records'].append(h)

    for f in active_flocks:
        h_data = flock_hatch_map.get(f.id)
        hatch_recs = h_data['records'] if h_data else []

        daily_stats = enrich_flock_data(f, f.logs, hatchability_data=hatch_recs)
        f.enriched_data = daily_stats # Cache for ISO Report with hatch data

        # Hatchery Enrichment
        if h_data:
            latest_hatch = h_data['latest']
            total_h = h_data['hatched_sum']
            total_s = h_data['set_sum']
        else:
            latest_hatch = None
            total_h = 0
            total_s = 0

        f.latest_hatch = latest_hatch
        f.latest_hatch_pct = latest_hatch.hatchability_pct if latest_hatch else 0.0

        f.cum_hatch_pct = (total_h / total_s * 100) if total_s > 0 else 0.0

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
            if last['date'] == today:
                f.has_log_today = True

            if getattr(f, 'calculated_phase', f.phase) in ['Brooding', 'Growing', 'Pre-lay']:
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

        stats_map = { d['date']: d for d in daily_stats }
        stats_today = stats_map.get(today)

        # Determine Display Data (Today or Latest)
        display_data = None
        if stats_today:
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
            stats_prev = None
            if display_data in daily_stats:
                idx = daily_stats.index(display_data)
                if idx > 0:
                    stats_prev = daily_stats[idx-1]
            else:
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

    # Analytics: Previous & Next Hatch Dates
    last_hatch, next_hatch = get_hatchery_analytics()

    # --- New ISO Reports ---
    # Year Filter Logic
    available_years_query = db.session.query(func.extract('year', DailyLog.date)).distinct().all()
    available_years = sorted([int(y[0]) for y in available_years_query if y[0]], reverse=True)
    if not available_years:
        available_years = [today.year]

    selected_year = request.args.get('year', type=int)
    if not selected_year:
        selected_year = available_years[0] if available_years else today.year

    active_tab = request.args.get('active_tab', 'overview')

    # Phase 2 Optimization: Use SQL-based aggregation
    # iso_data = get_iso_aggregated_data(active_flocks, target_year=selected_year)
    flock_ids = [f.id for f in active_flocks]
    iso_data = get_iso_aggregated_data_sql(flock_ids, selected_year)

    # Monthly Inventory Usage Calculation
    current_month_start = today.replace(day=1)
    if current_month_start.month == 1:
        last_month_start = current_month_start.replace(year=current_month_start.year - 1, month=12)
    else:
        last_month_start = current_month_start.replace(month=current_month_start.month - 1)

    inventory_items = InventoryItem.query.all()
    inventory_usage = []

    # We will get logs for current and last month
    logs_this_month = InventoryTransaction.query.filter(
        InventoryTransaction.transaction_date >= current_month_start,
        InventoryTransaction.transaction_type.in_(['Usage', 'Waste'])
    ).all()

    logs_last_month = InventoryTransaction.query.filter(
        InventoryTransaction.transaction_date >= last_month_start,
        InventoryTransaction.transaction_date < current_month_start,
        InventoryTransaction.transaction_type.in_(['Usage', 'Waste'])
    ).all()

    for item in inventory_items:
        used_this = sum(log.quantity for log in logs_this_month if log.inventory_item_id == item.id)
        used_last = sum(log.quantity for log in logs_last_month if log.inventory_item_id == item.id)

        inventory_usage.append({
            'name': item.name,
            'type': item.type,
            'current_stock': item.current_stock,
            'unit': item.unit,
            'used_this_month': round(used_this, 2),
            'used_last_month': round(used_last, 2)
        })

    return render_template('executive_dashboard.html',
                           active_flocks=active_flocks,
                           last_hatch=last_hatch,
                           next_hatch=next_hatch,
                           current_month=today.strftime('%B %Y'),
                           today=today,
                           inventory_usage=inventory_usage,
                           iso_data=iso_data,
                           available_years=available_years,
                           selected_year=selected_year,
                           active_tab=active_tab)
