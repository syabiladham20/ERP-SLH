import re

with open("app.py", "r") as f:
    content = f.read()

search = """        # Find or Create Farm
        farm_name = request.form.get('farm_name', '').strip()
        farm_id = None
        if farm_name:
            farm = Farm.query.filter_by(name=farm_name).first()
            if not farm:
                farm = Farm(name=farm_name)
                db.session.add(farm)
                db.session.commit()
                flash(f'Created new Farm: {farm_name}', 'info')
            farm_id = farm.id"""

replace = """        # Find or Create Farm
        farm_name = request.form.get('farm_name', '').strip()
        if not farm_name:
            flash('Error: Farm name is required.', 'danger')
            return redirect(url_for('manage_flocks'))

        farm_id = None
        farm = Farm.query.filter_by(name=farm_name).first()
        if not farm:
            farm = Farm(name=farm_name)
            db.session.add(farm)
            db.session.commit()
            flash(f'Created new Farm: {farm_name}', 'info')
        farm_id = farm.id"""

if search in content:
    content = content.replace(search, replace)
    with open("app.py", "w") as f:
        f.write(content)
    print("Patched app.py successfully (create flock).")
else:
    print("Could not find the target codeblock for create in app.py")
