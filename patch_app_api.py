with open('app.py', 'r') as f:
    content = f.read()

target_api_start = content.find("@app.route('/api/chart_data/<int:flock_id>')")
target_api_end = content.find("def get_flock_photos", target_api_start)

print("Actual API END:", target_api_end)
