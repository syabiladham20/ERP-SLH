from flask_login import LoginManager
from flask_migrate import Migrate

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.login_message = "Please log in to continue."
login_manager.login_message_category = "info"

migrate = Migrate()
