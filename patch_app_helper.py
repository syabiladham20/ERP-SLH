with open('app.py', 'r') as f:
    content = f.read()

start_idx = content.find('def get_chart_data(flock_id):')
end_idx = content.find('return jsonify', start_idx) + 500
print(content[start_idx:end_idx])
