from flask import Blueprint, request, redirect, url_for, render_template, flash, session
from flask_login import login_user, logout_user, current_user
from extensions import login_manager
from app import User, GlobalStandard

auth_bp = Blueprint('auth', __name__)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@auth_bp.before_app_request
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

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session.clear()
            login_user(user, remember=remember)
            session['user_id'] = user.id
            session['user_name'] = user.username
            session['user_dept'] = user.dept
            session['user_role'] = user.role
            session['is_admin'] = (user.role == 'Admin')

            if remember:
                session.permanent = True
            else:
                session.permanent = False

            flash(f"Welcome back, {user.username}!", "success")

            if user.dept == 'Hatchery':
                return redirect(url_for('hatchery_dashboard'))
            elif user.dept == 'Admin':
                return redirect(url_for('index'))
            elif user.dept == 'Management':
                return redirect(url_for('executive_dashboard'))
            else:
                return redirect(url_for('index'))
        else:
            flash("Invalid username or password.", "danger")

    return render_template('login_modern.html')

@auth_bp.route('/logout')
def logout():
    logout_user()
    session.clear()
    flash("You have been logged out.", "info")

    # Render a small intermediate page to clear localStorage, then redirect to login
    response = """
    <html>
        <body>
            <script>
                localStorage.removeItem("slh_offline_user_id");
                localStorage.removeItem("slh_offline_user_role");
                localStorage.removeItem("slh_offline_user_dept");
                window.location.href = "%s";
            </script>
        </body>
    </html>
    """ % url_for('auth.login')
    return response
