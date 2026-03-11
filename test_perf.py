import time
from sqlalchemy import text
from app import app, db, Flock, get_iso_aggregated_data_sql, DailyLog

def get_iso_aggregated_data_sql_optimized(flock_ids, target_year):
    if not flock_ids:
        return {'weekly': [], 'monthly': [], 'yearly': []}

    ids_tuple = tuple(flock_ids)
    if len(ids_tuple) == 1:
        ids_tuple = f"({ids_tuple[0]})"
    else:
        ids_tuple = str(ids_tuple)

    dialect = db.engine.name

    if dialect == 'sqlite':
        week_fmt = "strftime('%Y-%W', l.date)"
        month_fmt = "strftime('%Y-%m', l.date)"
        year_fmt = "strftime('%Y', l.date)"
        hatch_week_fmt = "strftime('%Y-%W', hatching_date)"
        hatch_month_fmt = "strftime('%Y-%m', hatching_date)"
        hatch_year_fmt = "strftime('%Y', hatching_date)"
    else:
        week_fmt = "to_char(l.date, 'IYYY-IW')"
        month_fmt = "to_char(l.date, 'YYYY-MM')"
        year_fmt = "to_char(l.date, 'YYYY')"
        hatch_week_fmt = "to_char(hatching_date, 'IYYY-IW')"
        hatch_month_fmt = "to_char(hatching_date, 'YYYY-MM')"
        hatch_year_fmt = "to_char(hatching_date, 'YYYY')"

    cte_sql = f"""
    WITH DailyStock AS (
        SELECT
            l.date,
            l.flock_id,
            {week_fmt} as iso_week,
            {month_fmt} as iso_month,
            {year_fmt} as iso_year,
            l.mortality_male + l.mortality_female + l.culls_male + l.culls_female as daily_loss,
            l.mortality_female as mort_f,
            l.eggs_collected,
            (l.feed_male + l.feed_female) as total_feed,
            f.intake_female + f.intake_male as intake_total,
            f.intake_female,
            f.start_of_lay_date,
            SUM(l.mortality_male + l.mortality_female + l.culls_male + l.culls_female)
                OVER (PARTITION BY l.flock_id ORDER BY l.date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) as cum_loss,
            SUM(l.mortality_female + l.culls_female)
                OVER (PARTITION BY l.flock_id ORDER BY l.date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) as cum_loss_f
        FROM daily_log l
        JOIN flock f ON l.flock_id = f.id
        WHERE l.flock_id IN {ids_tuple}
    ),
    EnrichedDaily AS (
        SELECT
            *,
            (intake_female - cum_loss_f) as stock_f_end,
            (intake_female - (cum_loss_f - (mort_f + 0))) as stock_f_start
        FROM DailyStock
    ),
    WeeklyLogs AS (
        SELECT
            'weekly' as type,
            iso_week as period,
            SUM(eggs_collected) as total_eggs,
            SUM(mort_f) as total_mort_f,
            SUM(stock_f_start) as total_hen_days,
            COUNT(DISTINCT date) as days_in_period
        FROM EnrichedDaily
        WHERE iso_year = :year
          AND start_of_lay_date IS NOT NULL
          AND date >= start_of_lay_date
        GROUP BY iso_week
    ),
    MonthlyLogs AS (
        SELECT
            'monthly' as type,
            iso_month as period,
            SUM(eggs_collected) as total_eggs,
            SUM(mort_f) as total_mort_f,
            SUM(stock_f_start) as total_hen_days,
            COUNT(DISTINCT date) as days_in_period
        FROM EnrichedDaily
        WHERE iso_year = :year
          AND start_of_lay_date IS NOT NULL
          AND date >= start_of_lay_date
        GROUP BY iso_month
    ),
    YearlyLogs AS (
        SELECT
            'yearly' as type,
            iso_year as period,
            SUM(eggs_collected) as total_eggs,
            SUM(mort_f) as total_mort_f,
            SUM(stock_f_start) as total_hen_days,
            COUNT(DISTINCT date) as days_in_period
        FROM EnrichedDaily
        WHERE iso_year = :year
          AND start_of_lay_date IS NOT NULL
          AND date >= start_of_lay_date
        GROUP BY iso_year
    )
    SELECT * FROM WeeklyLogs
    UNION ALL
    SELECT * FROM MonthlyLogs
    UNION ALL
    SELECT * FROM YearlyLogs
    """

    hatch_sql = f"""
    WITH WeeklyHatch AS (
        SELECT
            'weekly' as type,
            {hatch_week_fmt} as period,
            SUM(hatched_chicks) as hatched,
            SUM(egg_set) as egg_set
        FROM hatchability
        WHERE flock_id IN {ids_tuple} AND {hatch_year_fmt} = :year
        GROUP BY period
    ),
    MonthlyHatch AS (
        SELECT
            'monthly' as type,
            {hatch_month_fmt} as period,
            SUM(hatched_chicks) as hatched,
            SUM(egg_set) as egg_set
        FROM hatchability
        WHERE flock_id IN {ids_tuple} AND {hatch_year_fmt} = :year
        GROUP BY period
    ),
    YearlyHatch AS (
        SELECT
            'yearly' as type,
            {hatch_year_fmt} as period,
            SUM(hatched_chicks) as hatched,
            SUM(egg_set) as egg_set
        FROM hatchability
        WHERE flock_id IN {ids_tuple} AND {hatch_year_fmt} = :year
        GROUP BY period
    )
    SELECT * FROM WeeklyHatch
    UNION ALL
    SELECT * FROM MonthlyHatch
    UNION ALL
    SELECT * FROM YearlyHatch
    """

    # Execute only two queries instead of six
    all_logs = db.session.execute(text(cte_sql), {'year': str(target_year)}).fetchall()
    all_hatch = db.session.execute(text(hatch_sql), {'year': str(target_year)}).fetchall()

    # Process results
    results = {'weekly': [], 'monthly': [], 'yearly': []}

    # Organize hatch data: type -> period -> (hatched, egg_set)
    hatch_map = {'weekly': {}, 'monthly': {}, 'yearly': {}}
    for row in all_hatch:
        type_key, period, hatched, egg_set = row
        if period:
            hatch_map[type_key][period] = (hatched, egg_set)

    # Organize logs data
    logs_by_type = {'weekly': [], 'monthly': [], 'yearly': []}
    for row in all_logs:
        type_key, period, total_eggs, total_mort_f, total_hen_days, days_in_period = row
        if period:
            logs_by_type[type_key].append({
                'period': period,
                'total_eggs': total_eggs or 0,
                'total_mort_f': total_mort_f or 0,
                'total_hen_days': total_hen_days or 0,
                'days_in_period': days_in_period or 0
            })

    for key in ['weekly', 'monthly', 'yearly']:
        # Sort logs by period descending
        logs = sorted(logs_by_type[key], key=lambda x: x['period'], reverse=True)

        for log in logs:
            period = log['period']
            total_eggs = log['total_eggs']
            total_mort = log['total_mort_f']
            total_hen_days = log['total_hen_days']
            days_in_period = log['days_in_period']

            # Hatchery
            h_data = hatch_map[key].get(period)
            hatched = h_data[0] if h_data else 0
            set_cnt = h_data[1] if h_data else 0

            avg_stock = (total_hen_days / days_in_period) if days_in_period > 0 else 0
            mort_pct = (total_mort / avg_stock * 100) if avg_stock > 0 else 0
            egg_prod_pct = (total_eggs / total_hen_days * 100) if total_hen_days > 0 else 0
            hatch_pct = (hatched / set_cnt * 100) if set_cnt > 0 else 0

            results[key].append({
                'period': period,
                'avg_prod_females': int(avg_stock),
                'avg_female_stock': int(avg_stock),
                'total_eggs': total_eggs,
                'total_chicks': hatched,
                'mortality_pct': round(mort_pct, 2),
                'hatchability_pct': round(hatch_pct, 2),
                'overall_egg_prod_pct': round(egg_prod_pct, 2),
                'egg_production_pct': round(egg_prod_pct, 2)
            })

    return results

def run_benchmark():
    with app.app_context():
        log = DailyLog.query.first()
        target_year = log.date.year if log else 2025

        flocks = Flock.query.all()
        flock_ids = [f.id for f in flocks]

        if not flock_ids:
            return

        start = time.time()
        for _ in range(50):
            res1 = get_iso_aggregated_data_sql(flock_ids, target_year)
        end = time.time()

        time1 = end - start
        print(f"Original Elapsed: {time1:.4f} seconds")

        start = time.time()
        for _ in range(50):
            res2 = get_iso_aggregated_data_sql_optimized(flock_ids, target_year)
        end = time.time()

        time2 = end - start
        print(f"Optimized Elapsed: {time2:.4f} seconds")
        print(f"Improvement: {(time1 - time2) / time1 * 100:.2f}%")

        # Verify correctness
        assert res1['weekly'] == res2['weekly']
        assert res1['monthly'] == res2['monthly']
        assert res1['yearly'] == res2['yearly']
        print("Verification passed! Data matches exactly.")

if __name__ == '__main__':
    run_benchmark()
