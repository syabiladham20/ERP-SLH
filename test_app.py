import datetime
from metrics import aggregate_weekly_metrics, aggregate_monthly_metrics

def format_iso_data(all_enriched_data):
    weekly_agg = aggregate_weekly_metrics(all_enriched_data)
    monthly_agg = aggregate_monthly_metrics(all_enriched_data)

    iso_data_replacement = {
        'weekly': [],
        'monthly': [],
        'yearly': []
    }

    # Format weekly
    for ws in weekly_agg:
        iso_data_replacement['weekly'].append({
            'period': f"Week {ws['week']}",
            'avg_female_stock': int(ws['stock_female_start'] - ((ws['mortality_female'] + ws['culls_female']) / 2)),
            'total_eggs': ws['eggs_collected'],
            'total_chicks': ws['hatched_chicks'],
            'mortality_pct': ws['mortality_female_pct'] * 100,
            'hatchability_pct': ws['hatchability_pct'] * 100,
            'egg_production_pct': ws['egg_prod_pct'] * 100
        })

    # Format monthly
    for ms in monthly_agg:
        iso_data_replacement['monthly'].append({
            'period': ms['month'],
            'avg_female_stock': int(ms['stock_female_start'] - ((ms['mortality_female'] + ms['culls_female']) / 2)),
            'total_eggs': ms['eggs_collected'],
            'total_chicks': ms['hatched_chicks'],
            'mortality_pct': ms['mortality_female_pct'] * 100,
            'hatchability_pct': ms['hatchability_pct'] * 100,
            'egg_production_pct': ms['egg_prod_pct'] * 100
        })

    # Group by year for yearly
    yearly_stats = {}
    for d in all_enriched_data:
        y_key = str(d['date'].year)
        if y_key not in yearly_stats:
            yearly_stats[y_key] = {
                'period': y_key,
                'count': 0,
                'stock_female_start': d['stock_female_start'],
                'mortality_female': 0,
                'culls_female': 0,
                'eggs_collected': 0,
                'hatched_chicks': 0,
                'egg_set': 0
            }

        ys = yearly_stats[y_key]
        ys['count'] += 1
        ys['mortality_female'] += d['mortality_female']
        ys['culls_female'] += d['culls_female']
        ys['eggs_collected'] += d['eggs_collected']
        if d['hatched_chicks']: ys['hatched_chicks'] += d['hatched_chicks']
        if d['egg_set']: ys['egg_set'] += d['egg_set']

    for y_key in sorted(yearly_stats.keys()):
        ys = yearly_stats[y_key]
        avg_hen = ys['stock_female_start'] - ((ys['mortality_female'] + ys['culls_female']) / 2)
        mortality_pct = (ys['mortality_female'] / ys['stock_female_start'] * 100) if ys['stock_female_start'] > 0 else 0
        egg_prod_pct = (ys['eggs_collected'] / (avg_hen * ys['count']) * 100) if (avg_hen * ys['count']) > 0 else 0
        hatchability_pct = (ys['hatched_chicks'] / ys['egg_set'] * 100) if ys['egg_set'] > 0 else 0

        iso_data_replacement['yearly'].append({
            'period': y_key,
            'avg_female_stock': int(avg_hen),
            'total_eggs': ys['eggs_collected'],
            'total_chicks': ys['hatched_chicks'],
            'mortality_pct': mortality_pct,
            'hatchability_pct': hatchability_pct,
            'egg_production_pct': egg_prod_pct
        })

    return iso_data_replacement
