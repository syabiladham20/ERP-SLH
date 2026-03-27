from app import app, db, UIElement
with app.app_context():
    els = UIElement.query.all()
    for el in els:
        print(f"[{el.section}] {el.key}: is_visible={el.is_visible}")
