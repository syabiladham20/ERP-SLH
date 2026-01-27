@app.route('/flock/<int:id>/dashboard')
def flock_dashboard(id):
    flock = Flock.query.get_or_404(id)

    date_str = request.args.get('date')
    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = date.today()

    # Get Logs
    log_today = DailyLog.query.filter_by(flock_id=id, date=target_date).first()

    from datetime import timedelta
    log_prev = DailyLog.query.filter_by(flock_id=id, date=target_date - timedelta(days=1)).first()

    # Calculate Age
    age_days = (target_date - flock.intake_date).days
    age_week = (age_days // 7) + 1

    # Fetch Standard for this week
    standard = Standard.query.filter_by(week=age_week).first()

    # Pre-calc cumulatives for KPI
    # We need cumulative up to today
    all_logs = DailyLog.query.filter_by(flock_id=id).filter(DailyLog.date <= target_date).order_by(DailyLog.date.asc()).all()

    cum_mort_m = 0
    cum_mort_f = 0
    cum_cull_m = 0
    cum_cull_f = 0

    # Logic to split rearing/prod for dashboard if needed, or just total cum
    # Excel "Cum. Mort %" usually implies Total Cumulative unless specified.
    # User requirement: "Separate cumulative mortality... Include cum mortality in overview on top".
    # In dashboard rows: "Female Cum. Mort. %". Assuming Total or Phase based?
    # Given the dashboard is general, Total Cumulative from Intake is standard unless "Production Dashboard".
    # But if Phase is Production, maybe it shows Prod Cum?
    # Let's show Total Cum for now as it's safer, or show both if space.
    # Excel row 14: "Female Cum. Mort. %".

    start_m = flock.intake_male
    start_f = flock.intake_female

    for l in all_logs:
        cum_mort_m += l.mortality_male
        cum_mort_f += l.mortality_female
        cum_cull_m += l.culls_male
        cum_cull_f += l.culls_female

    curr_stock_m = start_m - cum_mort_m - cum_cull_m
    curr_stock_f = start_f - cum_mort_f - cum_cull_f

    # Prepare KPI Data Structure
    # { 'label': 'Female Mortality %', 'value': X, 'prev': Y, 'diff': X-Y, 'std': Z, 'status': 'ok/warning' }

    kpis = []

    def get_val(log, attr, default=0):
        return getattr(log, attr) if log else default

    def calc_pct(num, den):
        return (num / den * 100) if den > 0 else 0

    # 1. Female Mortality % (Daily)
    mort_f_today = calc_pct(get_val(log_today, 'mortality_male') + get_val(log_today, 'culls_male'), curr_stock_f) # Wait, formula?
    # Daily Mort % usually = Dead / Current * 100.
    # Excel says "Female Mortality %".

    # Let's use Mort only? or Depletion?
    # Usually Mortality % excludes culls. Depletion includes culls.
    # Excel has separate "Female Cull %". So here it's just Mortality.

    mort_f_val = calc_pct(get_val(log_today, 'mortality_female'), curr_stock_f)
    mort_f_prev = calc_pct(get_val(log_prev, 'mortality_female'), curr_stock_f + get_val(log_today, 'mortality_female')) # Approx prev stock

    std_mort_f = standard.std_mortality_female if standard else None

    kpis.append({
        'label': 'Female Mortality %',
        'value': mort_f_val,
        'prev': mort_f_prev,
        'unit': '%',
        'std': std_mort_f,
        'reverse_bad': True # Higher is bad
    })

    # 2. Female Cull %
    cull_f_val = calc_pct(get_val(log_today, 'culls_female'), curr_stock_f)
    cull_f_prev = calc_pct(get_val(log_prev, 'culls_female'), curr_stock_f)
    kpis.append({
        'label': 'Female Cull %',
        'value': cull_f_val,
        'prev': cull_f_prev,
        'unit': '%',
        'reverse_bad': True
    })

    # 3. Female Cum Mort %
    cum_mort_f_pct = calc_pct(cum_mort_f, start_f)
    # prev cum is cum - today's
    cum_mort_f_prev = calc_pct(cum_mort_f - get_val(log_today, 'mortality_female'), start_f)
    kpis.append({
        'label': 'Female Cum. Mort %',
        'value': cum_mort_f_pct,
        'prev': cum_mort_f_prev,
        'unit': '%',
        'reverse_bad': True
    })

    # 4. Egg Prod %
    eggs = get_val(log_today, 'eggs_collected')
    egg_prod = calc_pct(eggs, curr_stock_f)
    eggs_prev = get_val(log_prev, 'eggs_collected')
    egg_prod_prev = calc_pct(eggs_prev, curr_stock_f) # approx stock

    std_egg = standard.std_egg_prod if standard else None
    kpis.append({
        'label': 'Egg Production %',
        'value': egg_prod,
        'prev': egg_prod_prev,
        'unit': '%',
        'std': std_egg,
        'reverse_bad': False # Lower is bad
    })

    # 5. Body Weights
    bw_f = get_val(log_today, 'body_weight_female')
    bw_f_prev = get_val(log_prev, 'body_weight_female')
    std_bw_f = standard.std_bw_female if standard else None
    kpis.append({
        'label': 'Female BW (g)',
        'value': bw_f,
        'prev': bw_f_prev,
        'unit': 'g',
        'std': std_bw_f,
        'reverse_bad': False # Depends, but low is bad usually
    })

    return render_template('flock_kpi.html', flock=flock, kpis=kpis, target_date=target_date, age_week=age_week, age_days=age_days)
