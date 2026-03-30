import re

with open('app.py', 'r') as f:
    content = f.read()

# Fix login() function to use login_user
login_func_old = """
        if user and user.check_password(password):
            session.clear()
            session['user_id'] = user.id
            session['user_name'] = user.username
            session['user_dept'] = user.dept
            session['user_role'] = user.role
            session['is_admin'] = (user.role == 'Admin')

            if remember:
                session.permanent = True
            else:
                session.permanent = False
"""
login_func_new = """
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
"""
content = content.replace(login_func_old, login_func_new)

# Fix logout() function to use logout_user
logout_func_old = """
@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
"""
logout_func_new = """
@app.route('/logout')
def logout():
    logout_user()
    session.clear()
    flash("You have been logged out.", "info")
"""
content = content.replace(logout_func_old, logout_func_new)

# Update before_request and g.user
before_request_old = """
@app.before_request
def load_logged_in_user():
    # TEMPORARY FEATURE: Auto-login if login_required is False
    login_not_required = False
    try:
        gs = GlobalStandard.query.first()
        if gs and hasattr(gs, 'login_required') and not gs.login_required:
            login_not_required = True
    except Exception:
        pass # Table might not exist yet during initial setup/migration

    user_id = session.get('user_id')

    if login_not_required and not user_id:
        # Auto-login as Admin
        admin = User.query.filter_by(role='Admin').first()
        if not admin:
             # Fallback to username 'admin'
             admin = User.query.filter_by(username='admin').first()

        if admin:
            session.clear()
            session['user_id'] = admin.id
            session['user_name'] = admin.username
            session['user_dept'] = admin.dept
            session['user_role'] = admin.role
            session['is_admin'] = (admin.role == 'Admin')
            user_id = admin.id

    if user_id and isinstance(user_id, int):
        g.user = User.query.get(user_id)
    else:
        g.user = None
"""
before_request_new = """
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
"""
content = content.replace(before_request_old, before_request_new)


# Update g.user references to current_user
content = content.replace("g.user", "current_user")
content = content.replace("if current_user:\n        return redirect(url_for('index'))", "if current_user.is_authenticated:\n        return redirect(url_for('index'))")


# Remove the old custom login_required
custom_login_required_regex = re.compile(r"def login_required\(f\):\n.*?(?=\ndef dept_required)", re.DOTALL)
content = custom_login_required_regex.sub("", content)

# Update dept_required decorator to use current_user.dept instead of session['user_dept']
# Wait, let's keep session lookup if current_user isn't authenticated yet?
# Let's update dept_required to use current_user.
dept_required_old = """
def dept_required(required_dept):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_dept = session.get('user_dept')

            # Super Admin can access everything
            if user_dept == 'Admin':
                return f(*args, **kwargs)

            # Check if required_dept is a list/tuple
            if isinstance(required_dept, (list, tuple)):
                if user_dept in required_dept:
                    return f(*args, **kwargs)
            else:
                # If user matches required dept
                if user_dept == required_dept:
                    return f(*args, **kwargs)

            # If guest (None)
            if user_dept is None:
                if request.path == url_for('login'): # Avoid loop
                    return f(*args, **kwargs)

                # Prevent duplicate flash messages
                flashes = session.get('_flashes', [])
                if not any(category == 'info' and msg == "Please log in to continue." for category, msg in flashes):
                    flash("Please log in to continue.", "info")

                return redirect(url_for('login'))

            # If user is logged in but wrong department
            dept_str = ', '.join(required_dept) if isinstance(required_dept, (list, tuple)) else required_dept
            flash(f"Access Denied: You do not have permission to view the {dept_str} Department", "danger")

            # Redirect to their own dashboard
            if user_dept == 'Hatchery':
                return redirect(url_for('hatchery_dashboard'))
            elif user_dept == 'Farm':
                return redirect(url_for('index'))
            elif user_dept == 'Management':
                return redirect(url_for('executive_dashboard'))
            else:
                return redirect(url_for('login')) # Fallback

        return decorated_function
    return decorator
"""

dept_required_new = """
def dept_required(required_dept):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                if request.path == url_for('login'): # Avoid loop
                    return f(*args, **kwargs)

                # Prevent duplicate flash messages
                flashes = session.get('_flashes', [])
                if not any(category == 'info' and msg == "Please log in to continue." for category, msg in flashes):
                    flash("Please log in to continue.", "info")
                return redirect(url_for('login'))

            user_dept = current_user.dept

            # Super Admin can access everything
            if user_dept == 'Admin':
                return f(*args, **kwargs)

            # Check if required_dept is a list/tuple
            if isinstance(required_dept, (list, tuple)):
                if user_dept in required_dept:
                    return f(*args, **kwargs)
            else:
                # If user matches required dept
                if user_dept == required_dept:
                    return f(*args, **kwargs)

            # If user is logged in but wrong department
            dept_str = ', '.join(required_dept) if isinstance(required_dept, (list, tuple)) else required_dept
            flash(f"Access Denied: You do not have permission to view the {dept_str} Department", "danger")

            # Redirect to their own dashboard
            if user_dept == 'Hatchery':
                return redirect(url_for('hatchery_dashboard'))
            elif user_dept == 'Farm':
                return redirect(url_for('index'))
            elif user_dept == 'Management':
                return redirect(url_for('executive_dashboard'))
            else:
                return redirect(url_for('login')) # Fallback

        return decorated_function
    return decorator
"""
content = content.replace(dept_required_old, dept_required_new)

with open('app.py', 'w') as f:
    f.write(content)
