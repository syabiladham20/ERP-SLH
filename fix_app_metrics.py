import re

with open('app.py', 'r') as f:
    app_content = f.read()

# We need to insert the new metrics calculation into the dashboard_metrics dict inside calculate_flock_summary
old_return = """    return dashboard_metrics, summary_table"""

new_metrics_code = """
    # Mix in the new summary metrics from the latest day
    if daily_stats:
        latest = daily_stats[-1]
        mort_f = (latest.get('mortality_female_pct') or 0) + (latest.get('culls_female_pct') or 0)
        mort_m = (latest.get('mortality_male_pct') or 0) + (latest.get('culls_male_pct') or 0)

        dashboard_metrics.update({
            'egg_prod_pct': round(latest.get('egg_prod_pct', 0) or 0, 2),
            'hatch_egg_pct': round(latest.get('hatch_egg_pct', 0) or 0, 2),
            'female_depletion': round(mort_f, 2),
            'male_depletion': round(mort_m, 2),
            'feed_f': round(latest.get('feed_female_gp_bird', 0) or 0, 1),
            'feed_m': round(latest.get('feed_male_gp_bird', 0) or 0, 1),
            'water': round(latest.get('water_per_bird', 0) or 0, 1),
            'bw_f': latest.get('body_weight_female') or 0,
            'bw_m': latest.get('body_weight_male') or 0
        })
    else:
        dashboard_metrics.update({
            'egg_prod_pct': 0.0,
            'hatch_egg_pct': 0.0,
            'female_depletion': 0.0,
            'male_depletion': 0.0,
            'feed_f': 0.0,
            'feed_m': 0.0,
            'water': 0.0,
            'bw_f': 0,
            'bw_m': 0
        })

    return dashboard_metrics, summary_table
"""

if old_return in app_content:
    app_content = app_content.replace(old_return, new_metrics_code.strip('\n'))
    with open('app.py', 'w') as f:
        f.write(app_content)
    print("Metrics merged successfully")
else:
    print("Could not find the return statement to replace.")
