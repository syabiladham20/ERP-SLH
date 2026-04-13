import os
import json
from datetime import datetime, date
from flask import current_app as app, render_template, request, session
from flask_login import current_user, login_user, AnonymousUserMixin

from app.database import db
from app.models.models import User, UIElement, GlobalStandard, SystemAuditLog

def register_error_handlers(app):
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        import traceback
        error_details = traceback.format_exc() if app.debug else "An unexpected error occurred."
        return render_template('errors/500.html', error=error_details), 500
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

def register_template_filters(app):
    @app.template_filter('basename')
    def basename_filter(s):
        if not s:
            return None
        return os.path.basename(str(s).replace('\\', '/'))
    @app.template_filter('from_json')
    def from_json_filter(value):
        import json
        try:
            return json.loads(value)
        except:
            return {}
    @app.template_filter('date_fmt')
    def date_fmt_filter(value):
        if value is None:
            return ""
        if isinstance(value, str):
            # Try parsing common formats if string
            try:
                value = datetime.strptime(value, '%Y-%m-%d')
            except ValueError:
                return value
        if isinstance(value, (datetime, date)):
            return value.strftime('%d-%b-%Y')
        return value

def register_context_processors(app):
    @app.context_processor
    def inject_metadata():
        return {
            'version': APP_VERSION,
            'build_date': DISPLAY_DATE
        }
    @app.context_processor
    def inject_system_health():
        logs = []
        try:
            logs = SystemAuditLog.query.order_by(SystemAuditLog.timestamp.desc()).limit(3).all()
        except Exception:
            pass
        return dict(system_health_logs=logs)
    @app.context_processor
    def utility_processor():
        # Inject Effective Admin & Dept for Simulation
        real_is_admin = getattr(current_user, 'role', None) == 'Admin'
        hide_view = session.get('hide_admin_view', False)
        effective_is_admin = real_is_admin
        effective_dept = getattr(current_user, "dept", None)
        effective_role = getattr(current_user, "role", None)
        if real_is_admin and hide_view:
            effective_is_admin = False
            # Infer Dept/Role based on Context
            path = request.path
            if path.startswith('/executive'):
                 effective_dept = 'Management'
                 effective_role = 'Management'
            elif path.startswith('/hatchery') or 'hatchability' in path or 'hatch' in path:
                 # 'hatch' covers hatchery_dashboard, hatchery_charts, import_hatchability, etc.
                 effective_dept = 'Hatchery'
                 effective_role = 'Worker'
            else:
                 effective_dept = 'Farm'
                 effective_role = 'Worker'
        def get_partition_val(log, name, type_):
            if not log: return 0.0
            for pw in log.partition_weights:
                if pw.partition_name == name:
                    return pw.body_weight if type_ == 'bw' else pw.uniformity
            return 0.0
        def get_ui_elements(section):
            # Admin sees everything (sorted)
            # Standard users see only visible
            query = UIElement.query.filter_by(section=section).order_by(UIElement.order_index.asc())
            if not effective_is_admin:
                query = query.filter_by(is_visible=True)
            return query.all()
        from flask import g
        return dict(get_partition_val=get_partition_val,
                    get_ui_elements=get_ui_elements,
                    is_admin=effective_is_admin,
                    real_is_admin=real_is_admin,
                    user_dept=effective_dept,
                    user_role=effective_role,
                    is_debug=app.debug,
                    current_user=current_user if hasattr(g, 'user') and current_user else AnonymousUserMixin())

def register_request_hooks(app):
    @app.before_request
    def load_logged_in_user():
        # Keep the global variables set based on current_user
        if current_user.is_authenticated:
            session['user_id'] = current_user.id
            session['user_name'] = current_user.username
            session['user_dept'] = current_user.dept
            session['user_role'] = current_user.role
            session['is_admin'] = (current_user.role == 'Admin')
        # TEMPORARY FEATURE: Auto-login if login_required is False
        login_not_required = False
        try:
            gs = GlobalStandard.query.first()
            if gs and hasattr(gs, 'login_required') and not gs.login_required:
                login_not_required = True
        except Exception:
            pass # Table might not exist yet during initial setup/migration
        if login_not_required and not current_user.is_authenticated:
            # Auto-login as Admin
            admin = User.query.filter_by(role='Admin').first()
            if not admin:
                 # Fallback to username 'admin'
                 admin = User.query.filter_by(username='admin').first()
            if admin:
                login_user(admin)
                session['user_id'] = admin.id
                session['user_name'] = admin.username
                session['user_dept'] = admin.dept
                session['user_role'] = admin.role
                session['is_admin'] = (admin.role == 'Admin')

# Version config
import os
from datetime import datetime
BUILD_TIME_FILE = os.path.join(os.path.dirname(__file__), '..', '.build_time')
if os.path.exists(BUILD_TIME_FILE):
    with open(BUILD_TIME_FILE, 'r') as f:
        ts = float(f.read().strip())
        BUILD_TIME = datetime.fromtimestamp(ts)
else:
    BUILD_TIME = datetime.now()

APP_VERSION = BUILD_TIME.strftime("%Y%m%d%H%M")
DISPLAY_DATE = BUILD_TIME.strftime("%B %d, %Y")
