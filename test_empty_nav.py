from app import app, db, UIElement
from flask import session
import logging
import io

log_stream = io.StringIO()
handler = logging.StreamHandler(log_stream)
app.logger.addHandler(handler)
app.logger.setLevel(logging.WARNING)

with app.test_request_context('/'):
    # Simulate non-admin request
    session['is_admin'] = True
    session['hide_admin_view'] = True

    with app.app_context():
        # Temporarily hide all nav elements to trigger the warning
        els = UIElement.query.filter_by(section='navbar_main').all()
        for el in els:
            el.is_visible = False
        db.session.commit()

        # Test utility processor injection
        @app.route('/test_processor')
        def test_route():
            return "Test"

        # Get processor output
        processor_dict = app.jinja_env.globals.copy()
        for func in app.template_context_processors[None]:
            processor_dict.update(func())

        get_ui_elements = processor_dict['get_ui_elements']

        # Call it for navbar_main
        elements = get_ui_elements('navbar_main')
        print(f"Elements: {elements}")
        print(f"Log Output:\n{log_stream.getvalue()}")

        # Revert changes
        for el in els:
            el.is_visible = True
        db.session.commit()
