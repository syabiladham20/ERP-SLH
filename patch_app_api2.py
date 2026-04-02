with open('app.py', 'r') as f:
    content = f.read()

target_api_start = content.find("@app.route('/api/chart_data/<int:flock_id>')")
# Find the next @app.route
next_route_start = content.find("@app.route", target_api_start + 10)
print("API START:", target_api_start)
print("Next Route:", next_route_start)

# Let's write the helper function right above `/api/chart_data`
