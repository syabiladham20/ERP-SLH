import base64
from werkzeug.utils import secure_filename

@app.route('/api/reports/backup', methods=['POST'])
@login_required
def backup_report_image():
    data = request.json
    if not data or 'image' not in data or 'date' not in data or 'house' not in data or 'age' not in data:
        return jsonify({'error': 'Missing data'}), 400

    image_data = data['image']
    if ',' in image_data:
        image_data = image_data.split(',')[1]

    date_str = data['date'] # YYYY-MM-DD
    house_name = data['house']
    age_week = data['age']

    filename = f"{date_str}_{secure_filename(house_name)}_W{age_week}.jpg"

    reports_dir = os.path.join(app.root_path, 'static', 'reports')
    if not os.path.exists(reports_dir):
        os.makedirs(reports_dir)

    filepath = os.path.join(reports_dir, filename)

    try:
        with open(filepath, "wb") as fh:
            fh.write(base64.b64decode(image_data))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    try:
        current_time = datetime.now()
        for f in os.listdir(reports_dir):
            f_path = os.path.join(reports_dir, f)
            if os.path.isfile(f_path):
                mtime = datetime.fromtimestamp(os.path.getmtime(f_path))
                if (current_time - mtime).days > 7:
                    os.remove(f_path)
    except Exception as e:
        pass

    return jsonify({'success': True, 'path': f'/static/reports/{filename}'})
