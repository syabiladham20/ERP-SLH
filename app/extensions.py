from flask_caching import Cache
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import current_user

def user_id_or_ip():
    if current_user.is_authenticated:
        return str(current_user.id)
    return get_remote_address()

def exempt_admin():
    if current_user.is_authenticated and current_user.role == 'Admin':
        return True
    return False

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = "Please log in to continue."
login_manager.login_message_category = "info"

@login_manager.unauthorized_handler
def unauthorized():
    from flask import request, jsonify, redirect, url_for
    if request.path.startswith('/api/'):
        return jsonify({"error": "Unauthorized"}), 401
    return redirect(url_for('auth.login', next=request.path))

migrate = Migrate()
csrf = CSRFProtect()
limiter = Limiter(key_func=user_id_or_ip, default_limits=["200 per day", "50 per hour"])
limiter.request_filter(exempt_admin)

cache = Cache()
