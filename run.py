from app import create_app
from app.database import db
from app.services.seed_service import init_ui_elements

app = create_app()

with app.app_context():
    try:
        db.create_all()
        init_ui_elements(commit=True)
    except Exception as e:
        app.logger.warning(f"Error during initialization: {e}")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
