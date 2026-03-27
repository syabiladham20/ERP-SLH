from app import app, db, UIElement

with app.app_context():
    elements = UIElement.query.filter_by(section='navbar_main').all()
    for el in elements:
        print(f"ID: {el.id}, Key: {el.key}, Label: {el.label}, Section: {el.section}, Visible: {el.is_visible}")
