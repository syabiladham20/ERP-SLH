import re

with open('app.py', 'r') as f:
    content = f.read()

# We need to add the inventory_usage to the context
# Find the end of executive_dashboard route
target = """    flock_ids = [f.id for f in active_flocks]
    iso_data = get_iso_aggregated_data_sql(flock_ids, selected_year)

    return render_template('executive_dashboard.html',"""

replacement = """    flock_ids = [f.id for f in active_flocks]
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
    logs_this_month = InventoryLog.query.filter(InventoryLog.date >= current_month_start).all()
    logs_last_month = InventoryLog.query.filter(InventoryLog.date >= last_month_start, InventoryLog.date < current_month_start).all()

    for item in inventory_items:
        used_this = sum(abs(log.quantity_change) for log in logs_this_month if log.item_id == item.id and log.quantity_change < 0)
        used_last = sum(abs(log.quantity_change) for log in logs_last_month if log.item_id == item.id and log.quantity_change < 0)

        inventory_usage.append({
            'name': item.name,
            'type': item.type,
            'current_stock': item.current_stock,
            'unit': item.unit,
            'used_this_month': round(used_this, 2),
            'used_last_month': round(used_last, 2)
        })

    return render_template('executive_dashboard.html',"""

content = content.replace(target, replacement)

# Fix render_template args to include inventory_usage and remove low_stock_items
target_args = """                           today=today,
                           low_stock_items=low_stock_items,
                           low_stock_count=low_stock_count,
                           normal_stock_items=normal_stock_items,
                           iso_data=iso_data,"""
replacement_args = """                           today=today,
                           inventory_usage=inventory_usage,
                           iso_data=iso_data,"""
content = content.replace(target_args, replacement_args)

with open('app.py', 'w') as f:
    f.write(content)
