from app.extensions import limiter
from flask import render_template, request, redirect, flash, url_for, session
from flask_login import login_required, current_user, login_user, logout_user
from app.models.models import *

def register_auth_routes(app):

    from app.utils import safe_commit

    @app.route('/change_password', methods=['GET', 'POST'])
    @login_required
    def change_password():
        if not current_user.id:
            return redirect(url_for('login'))

        if request.method == 'POST':
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')

            user = User.query.get(session['user_id'])

            if not user or not user.check_password(current_password):
                flash("Incorrect current password.", "danger")
            elif new_password != confirm_password:
                flash("New passwords do not match.", "danger")
            else:
                user.set_password(new_password)
                safe_commit()
                flash("Password updated successfully.", "success")
                return redirect(url_for('index'))

        return render_template('change_password.html')

    @app.route('/logout')
    def logout():
        session.clear()
        logout_user()
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
        """ % url_for('login')
        return response

    @app.route('/login', methods=['GET', 'POST'])
    @limiter.limit("5 per minute")
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
