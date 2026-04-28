from flask_caching import Cache
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

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
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day", "50 per hour"])

cache = Cache()
