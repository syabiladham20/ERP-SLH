with open('templates/executive_dashboard.html', 'r') as f:
    content = f.read()

import re

# Insert the Inventory Status tab into the nav
content = content.replace(
    '''<li class="nav-item">\n    <button class="nav-link {% if active_tab == 'weekly_iso' %}active{% endif %}" data-bs-toggle="tab" data-bs-target="#weekly_iso">Weekly ISO</button>\n  </li>''',
    '''<li class="nav-item">\n    <button class="nav-link {% if active_tab == 'inventory_status' %}active{% endif %}" data-bs-toggle="tab" data-bs-target="#inventory_status">Inventory Status</button>\n  </li>\n  <li class="nav-item">\n    <button class="nav-link {% if active_tab == 'weekly_iso' %}active{% endif %}" data-bs-toggle="tab" data-bs-target="#weekly_iso">Weekly ISO</button>\n  </li>'''
)

# Insert the Inventory Status tab content panel after the overview tab
inventory_tab = """
  <!-- Inventory Status Tab -->
  <div class="tab-pane fade {% if active_tab == 'inventory_status' %}show active{% endif %}" id="inventory_status">
      <div class="card">
          <div class="card-header">
              <h5>Inventory Monthly Usage</h5>
          </div>
          <div class="card-body">
              <div class="table-responsive table-responsive-sticky">
                  <table class="table table-striped table-hover text-center">
                      <thead class="sticky-table-header">
                          <tr>
                              <th>Item Name</th>
                              <th>Type</th>
                              <th>Current Stock</th>
                              <th>Used This Month</th>
                              <th>Used Last Month</th>
                          </tr>
                      </thead>
                      <tbody>
                          {% for row in inventory_usage %}
                          <tr>
                              <td>{{ row.name }}</td>
                              <td>{{ row.type }}</td>
                              <td>{{ row.current_stock }} {{ row.unit }}</td>
                              <td class="text-danger">-{{ row.used_this_month }} {{ row.unit }}</td>
                              <td class="text-danger">-{{ row.used_last_month }} {{ row.unit }}</td>
                          </tr>
                          {% else %}
                          <tr><td colspan="5">No inventory data available.</td></tr>
                          {% endfor %}
                      </tbody>
                  </table>
              </div>
          </div>
      </div>
  </div>
"""

content = content.replace(
    '''<!-- Weekly ISO Tab -->''',
    inventory_tab + '\n  <!-- Weekly ISO Tab -->'
)

with open('templates/executive_dashboard.html', 'w') as f:
    f.write(content)
