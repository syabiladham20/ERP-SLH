import re

with open("app.py", "r") as f:
    content = f.read()

search = """        # Farm Update
        farm_name = request.form.get('farm_name', '').strip()
        if farm_name:
            farm = Farm.query.filter_by(name=farm_name).first()
            if not farm:
                farm = Farm(name=farm_name)
                db.session.add(farm)
                db.session.commit()
            flock.farm_id = farm.id
        else:
            flock.farm_id = None"""

replace = """        # Farm Update
        farm_name = request.form.get('farm_name', '').strip()
        if not farm_name:
            flash('Error: Farm name is required.', 'danger')
            return render_template('flock_edit.html', flock=flock)

        farm = Farm.query.filter_by(name=farm_name).first()
        if not farm:
            farm = Farm(name=farm_name)
            db.session.add(farm)
            db.session.commit()
        flock.farm_id = farm.id"""

if search in content:
    content = content.replace(search, replace)
    with open("app.py", "w") as f:
        f.write(content)
    print("Patched app.py successfully (edit flock).")
else:
    print("Could not find the target codeblock for edit in app.py")
