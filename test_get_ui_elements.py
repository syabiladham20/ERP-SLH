from app import app, db, UIElement
from flask import session

with app.test_request_context('/'):
    # Simulate non-admin request
    session['is_admin'] = True
    session['hide_admin_view'] = True

    with app.app_context():
        real_is_admin = session.get('is_admin', False)
        hide_view = session.get('hide_admin_view', False)

        effective_is_admin = real_is_admin
        if real_is_admin and hide_view:
            effective_is_admin = False

        print(f"Effective is admin: {effective_is_admin}")

        query = UIElement.query.filter_by(section='navbar_main').order_by(UIElement.order_index.asc())
        if not effective_is_admin:
            query = query.filter_by(is_visible=True)

        elements = query.all()
        print(f"Elements length: {len(elements)}")
        for el in elements:
             print(f"- {el.label} (Visible: {el.is_visible})")
