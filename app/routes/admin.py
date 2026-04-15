import time
from werkzeug.utils import secure_filename
from flask import render_template, request, redirect, flash, url_for, session, jsonify
from flask_login import login_required, current_user
from app.database import db
from app.models.models import *
from werkzeug.security import check_password_hash
import os

def register_admin_routes(app):

    from app.utils import safe_commit, send_push_alert, dept_required, round_to_whole
    from app.services.data_service import process_import
    from app.services.seed_service import seed_standards_from_file, seed_arbor_acres_standards

    @app.route('/import', methods=['GET', 'POST'])
    @login_required
    @dept_required('Farm')
    def import_data():
        if request.method == 'POST':
            # Check for Confirmation
            confirm_files = request.form.getlist('confirm_files')
            if confirm_files:
                results = []
                errors = []

                for confirm_filename in confirm_files:
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'temp', confirm_filename)
                    if not os.path.exists(filepath):
                        errors.append(f"{confirm_filename}: File not found.")
                        continue

                    try:
                        process_import(filepath, commit=True, preview=False)
                        os.remove(filepath)
                        results.append(confirm_filename)
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        errors.append(f"{confirm_filename}: {str(e)}")

                if results:
                    flash(f"Successfully imported {len(results)} files.", 'success')
                if errors:
                    for err in errors:
                        flash(f"Error: {err}", 'danger')

                return redirect(url_for('index'))

            if 'files' not in request.files:
                flash('No file part', 'danger')
                return redirect(request.url)

            files = request.files.getlist('files')
            if not files or files[0].filename == '':
                flash('No selected files', 'danger')
                return redirect(request.url)

            all_changes = []
            all_warnings = []
            temp_filenames = []

            for file in files:
                if file and file.filename.endswith('.xlsx'):
                    try:
                        # Save to temp
                        safe_name = secure_filename(f"{int(time.time())}_{file.filename}")
                        temp_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'temp')
                        os.makedirs(temp_dir, exist_ok=True)
                        filepath = os.path.join(temp_dir, safe_name)
                        file.save(filepath)
                        temp_filenames.append(safe_name)

                        changes, warnings = process_import(filepath, commit=False, preview=True)

                        # Add source filename to changes
                        for c in changes:
                            c['source_file'] = file.filename

                        all_changes.extend(changes)

                        # Prefix warnings with filename
                        for w in warnings:
                            all_warnings.append(f"[{file.filename}] {w}")

                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        flash(f"{file.filename}: {str(e)}", 'danger')
                        return redirect(request.url)
                else:
                    if file.filename:
                        flash(f"{file.filename}: Invalid type (must be .xlsx)", 'danger')
                        return redirect(request.url)

            if all_changes:
                return render_template('import_preview.html', changes=all_changes, warnings=all_warnings, filenames=temp_filenames)

            flash("No valid data found to import.", "warning")
            return redirect(url_for('index'))

        return render_template('import.html')

    @app.route('/admin/houses/delete/<int:id>', methods=['POST'])
    @login_required
    def admin_house_delete(id):
        if not current_user.role == 'Admin': return redirect(url_for('index'))

        house = House.query.get_or_404(id)
        if Flock.query.filter_by(house_id=id).count() > 0:
            flash(f"Cannot delete House '{house.name}' because it has flocks associated with it.", "danger")
        else:
            db.session.delete(house)
            safe_commit()
            flash(f"House '{house.name}' deleted.", "info")

        return redirect(url_for('admin_houses'))

    @app.route('/admin/houses/edit/<int:id>', methods=['POST'])
    @login_required
    def admin_house_edit(id):
        if not current_user.role == 'Admin': return redirect(url_for('index'))

        house = House.query.get_or_404(id)
        new_name = request.form.get('name').strip()

        if not new_name:
            flash("New name is required.", "danger")
        elif new_name != house.name and House.query.filter_by(name=new_name).first():
            flash(f"House '{new_name}' already exists.", "warning")
        else:
            old_name = house.name
            house.name = new_name
            safe_commit()
            flash(f"Renamed House '{old_name}' to '{new_name}'.", "success")

        return redirect(url_for('admin_houses'))

    @app.route('/admin/houses/add', methods=['POST'])
    @login_required
    def admin_house_add():
        if not current_user.role == 'Admin': return redirect(url_for('index'))

        name = request.form.get('name').strip()
        if not name:
            flash("House name is required.", "danger")
        elif House.query.filter_by(name=name).first():
            flash(f"House '{name}' already exists.", "warning")
        else:
            db.session.add(House(name=name))
            safe_commit()
            flash(f"House '{name}' added.", "success")

        return redirect(url_for('admin_houses'))

    @app.route('/admin/houses')
    @login_required
    def admin_houses():
        if not current_user.role == 'Admin':
            flash("Access Denied: Admin only.", "danger")
            return redirect(url_for('index'))

        houses = House.query.order_by(House.name).all()

        # Optimize N+1 Query: Bulk fetch houses that have flocks
        # We query for distinct house_ids from the Flock table
        houses_with_flocks = set(f[0] for f in db.session.query(Flock.house_id).distinct().all())

        # Check if houses can be deleted (no flocks)
        for h in houses:
            h.can_delete = h.id not in houses_with_flocks

        return render_template('admin/houses.html', houses=houses)

    @app.route('/admin/performance_report')
    @login_required
    def admin_performance_report():
        if not current_user.role == 'Admin':
            return redirect(url_for('index'))

        return render_template('admin/performance_report.html')

    @app.route('/admin/toggle_login', methods=['POST'])
    @login_required
    def toggle_login():
        if not current_user.role == 'Admin':
            return redirect(url_for('index'))

        gs = GlobalStandard.query.first()
        if not gs:
            gs = GlobalStandard()
            db.session.add(gs)

        # Toggle
        current = gs.login_required if hasattr(gs, 'login_required') else True
        gs.login_required = not current
        safe_commit()

        status = "ON" if gs.login_required else "OFF"

        if gs.login_required:
            session.clear()
            flash("Login Page enabled. Please log in.", "info")
            return redirect(url_for('login'))
        else:
            flash(f"Login Page turned {status}.", "warning")

        return redirect(url_for('admin_control_panel'))

    @app.route('/change_theme', methods=['POST'])
    def change_theme():
        if not current_user.id:
            flash("You must be logged in to change your theme.", "warning")
            return redirect(url_for('login'))

        user = User.query.get(session['user_id'])
        if user:
            theme = request.form.get('theme', 'base_tabler.html')
            # Validate theme input to avoid arbitrary file injection
            valid_themes = [
                'base_tabler.html', 'base_argon.html', 'base_volt.html',
                'base_horizon.html', 'base_material.html', 'base_soft.html',
                'base_lightblue.html', 'base_bw.html'
            ]
            if theme in valid_themes:
                user.theme = theme
                safe_commit()
                flash("Theme successfully updated.", "success")
            else:
                flash("Invalid theme selected.", "danger")

        return redirect(request.referrer or url_for('index'))

    @app.route('/admin/control-panel')
    @login_required
    def admin_control_panel():
        if not current_user.role == 'Admin':
            flash("Access Denied: Admin only.", "danger")
            return redirect(url_for('index'))

        gs = GlobalStandard.query.first()
        login_required = gs.login_required if gs and hasattr(gs, 'login_required') else True

        return render_template('admin/control_panel.html', login_required=login_required)

    @app.route('/admin/ui', methods=['GET', 'POST'])
    @login_required
    def admin_ui_update():
        if not current_user.role == 'Admin':
            return redirect(url_for('index'))

        if request.method == 'POST':
            # Process updates
            # Form data: id[], order_{id}, label_{id}, visible_{id}
            ids = request.form.getlist('id[]')

            int_ids = [int(id_str) for id_str in ids if id_str.isdigit()]
            ui_elements = UIElement.query.filter(UIElement.id.in_(int_ids)).all()
            ui_element_dict = {elem.id: elem for elem in ui_elements}

            for id_str in ids:
                eid = int(id_str) if id_str.isdigit() else 0
                elem = ui_element_dict.get(eid)
                if not elem: continue

                # Update Label
                label = request.form.get(f'label_{eid}')
                if label: elem.label = label

                # Update Order
                order = request.form.get(f'order_{eid}')
                if order and order.isdigit():
                    elem.order_index = int(order)

                # Update Visibility
                # Checkboxes only send value if checked.
                is_vis = request.form.get(f'visible_{eid}')
                elem.is_visible = (is_vis is not None)

            safe_commit()
            flash('UI configuration updated.', 'success')
            return redirect(url_for('admin_ui_update'))

        # GET: Fetch all elements grouped by section
        elements = {}
        all_elems = UIElement.query.order_by(UIElement.order_index.asc()).all()
        for e in all_elems:
            if e.section not in elements:
                elements[e.section] = []
            elements[e.section].append(e)

        return render_template('admin/ui_manager.html', elements=elements)

    @app.route('/toggle_admin_view')
    @login_required
    def toggle_admin_view():
        if not current_user.role == 'Admin':
            flash("Unauthorized.", "danger")
            return redirect(url_for('index'))

        session['hide_admin_view'] = not session.get('hide_admin_view', False)
        return redirect(request.referrer or url_for('index'))

    @app.route('/feed_codes/delete/<int:id>', methods=['POST'])
    @login_required
    @dept_required('Farm')
    def delete_feed_code(id):
        fc = FeedCode.query.get_or_404(id)
        db.session.delete(fc)
        safe_commit()
        flash(f'Feed Code {fc.code} deleted.', 'info')
        return redirect(url_for('manage_feed_codes'))

    @app.route('/feed_codes', methods=['GET', 'POST'])
    @login_required
    @dept_required('Farm')
    def manage_feed_codes():
        if request.method == 'POST':
            code = request.form.get('code').strip()
            if code:
                existing = FeedCode.query.filter_by(code=code).first()
                if existing:
                    flash(f'Feed Code {code} already exists.', 'warning')
                else:
                    db.session.add(FeedCode(code=code))
                    safe_commit()
                    flash(f'Feed Code {code} added.', 'success')
            return redirect(url_for('manage_feed_codes'))

        if FeedCode.query.count() == 0:
            default_codes = ['161C', '162C', '163C', '168C', '169C', '170P', '171P', '172P']
            for c in default_codes:
                db.session.add(FeedCode(code=c))
            safe_commit()

        codes = FeedCode.query.order_by(FeedCode.code.asc()).all()
        return render_template('feed_codes.html', codes=codes)

    @app.route('/standards', methods=['GET', 'POST'])
    @login_required
    @dept_required('Farm')
    def manage_standards():
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'add':
                week_val = request.form.get('week')
                if not week_val or not week_val.isdigit():
                    flash('Invalid or missing week number.', 'danger')
                    return redirect(url_for('manage_standards'))

                pw_val = request.form.get('production_week')
                prod_week = int(pw_val) if pw_val and pw_val.isdigit() else None

                s = Standard(
                    week=int(week_val),
                    production_week=prod_week,
                    std_mortality_male=float(request.form.get('std_mortality_male') or 0),
                    std_mortality_female=float(request.form.get('std_mortality_female') or 0),
                    std_bw_male=round_to_whole(request.form.get('std_bw_male')),
                    std_bw_female=round_to_whole(request.form.get('std_bw_female')),
                    std_egg_prod=float(request.form.get('std_egg_prod') or 0),
                    std_egg_weight=float(request.form.get('std_egg_weight') or 0),
                    std_hatchability=float(request.form.get('std_hatchability') or 0),
                    std_cum_eggs_hha=float(request.form.get('std_cum_eggs_hha') or 0),
                    std_cum_hatching_eggs_hha=float(request.form.get('std_cum_hatching_eggs_hha') or 0),
                    std_cum_chicks_hha=float(request.form.get('std_cum_chicks_hha') or 0)
                )
                db.session.add(s)
                safe_commit()
                flash('Standard added.', 'success')
            elif action == 'update':
                s_id = request.form.get('id')
                s = Standard.query.get(s_id)
                if s:
                    pw_val = request.form.get('production_week')
                    s.production_week = int(pw_val) if pw_val and pw_val.isdigit() else None

                    s.std_mortality_male=float(request.form.get('std_mortality_male') or 0)
                    s.std_mortality_female=float(request.form.get('std_mortality_female') or 0)
                    s.std_bw_male=round_to_whole(request.form.get('std_bw_male'))
                    s.std_bw_female=round_to_whole(request.form.get('std_bw_female'))
                    s.std_egg_prod=float(request.form.get('std_egg_prod') or 0)
                    s.std_egg_weight=float(request.form.get('std_egg_weight') or 0)
                    s.std_hatchability=float(request.form.get('std_hatchability') or 0)
                    s.std_cum_eggs_hha=float(request.form.get('std_cum_eggs_hha') or 0)
                    s.std_cum_hatching_eggs_hha=float(request.form.get('std_cum_hatching_eggs_hha') or 0)
                    s.std_cum_chicks_hha=float(request.form.get('std_cum_chicks_hha') or 0)

                    safe_commit()
                    flash(f'Standard for Week {s.week} updated.', 'success')
                else:
                    flash('Standard not found.', 'danger')

            elif action == 'update_global':
                gs = GlobalStandard.query.first()
                if not gs:
                    gs = GlobalStandard()
                    db.session.add(gs)

                gs.std_mortality_daily = float(request.form.get('std_mortality_daily') or 0.05)
                gs.std_mortality_weekly = float(request.form.get('std_mortality_weekly') or 0.3)
                gs.std_hatching_egg_pct = float(request.form.get('std_hatching_egg_pct') or 96.0)
                safe_commit()
                flash('Global standards updated.', 'success')

            elif action == 'seed_standards':
                success, message = seed_standards_from_file()
                if success:
                    flash(message, 'success')
                else:
                    flash(message, 'danger')
            elif action == 'seed_arbor_acres':
                success, message = seed_arbor_acres_standards()
                if success:
                    flash(message, 'success')
                else:
                    flash(message, 'danger')

            return redirect(url_for('manage_standards'))

        standards = Standard.query.order_by(Standard.week.asc()).all()
        global_std = GlobalStandard.query.first()
        if not global_std:
            global_std = GlobalStandard() # Default values from model

        return render_template('standards.html', standards=standards, global_std=global_std)

    @app.route('/admin/project_report')
    @login_required
    def admin_project_report():
        if not current_user.role == 'Admin' and current_user.role != 'Management':
            flash("Access Denied: Admin or Management View Only.", "danger")
            return redirect(url_for('index'))
        return render_template('admin/project_report.html')

    @app.route('/admin/users/reset_password/<int:user_id>', methods=['POST'])
    @login_required
    def admin_user_reset_password(user_id):
        if not current_user.role == 'Admin': return redirect(url_for('index'))

        user = User.query.get_or_404(user_id)
        new_pass = request.form.get('new_password')
        if new_pass:
            user.set_password(new_pass)
            safe_commit()
            flash(f"Password for {user.username} has been reset.", "success")
        else:
            flash("Password cannot be empty.", "danger")
        return redirect(url_for('admin_users'))

    @app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
    @login_required
    def admin_user_delete(user_id):
        if not current_user.role == 'Admin': return redirect(url_for('index'))

        user = User.query.get_or_404(user_id)
        if user.id == current_user.id:
            flash("Cannot delete yourself.", "danger")
        else:
            db.session.delete(user)
            safe_commit()
            flash(f"User {user.username} deleted.", "info")
        return redirect(url_for('admin_users'))

    @app.route('/admin/users/edit/<int:user_id>', methods=['POST'])
    @login_required
    def admin_user_edit(user_id):
        if not current_user.role == 'Admin': return redirect(url_for('index'))

        user = User.query.get_or_404(user_id)
        name = request.form.get('name')
        dept = request.form.get('dept')
        role = request.form.get('role')

        user.name = name
        user.dept = dept
        user.role = role
        safe_commit()

        if user.id == current_user.id:
            session['user_name'] = user.name if user.name else user.username

        flash(f"User {user.username} updated.", "success")
        return redirect(url_for('admin_users'))

    @app.route('/admin/users/add', methods=['POST'])
    @login_required
    def admin_user_add():
        if not current_user.role == 'Admin': return redirect(url_for('index'))

        username = request.form.get('username')
        name = request.form.get('name')
        password = request.form.get('password')
        dept = request.form.get('dept')
        role = request.form.get('role')
        farm_id = request.form.get('farm_id')

        if farm_id == '':
            farm_id = None

        if User.query.filter_by(username=username).first():
            flash(f"User {username} already exists.", "warning")
        else:
            u = User(username=username, name=name, dept=dept, role=role, farm_id=farm_id)
            u.set_password(password)
            db.session.add(u)
            safe_commit()
            flash(f"User {username} added.", "success")
        return redirect(url_for('admin_users'))

    @app.route('/admin/users')
    @login_required
    def admin_users():
        if not current_user.role == 'Admin':
            flash("Access Denied.", "danger")
            return redirect(url_for('index'))
        users = User.query.order_by(User.username).all()
        return render_template('admin/users.html', users=users)

    @app.route('/admin/rules/delete/<int:id>', methods=['POST'])
    def delete_notification_rule(id):
        if not current_user.role == 'Admin' and current_user.role != 'Management':
            flash("Access Denied.", "danger")
            return redirect(url_for('index'))

        rule = NotificationRule.query.get_or_404(id)
        db.session.delete(rule)
        safe_commit()
        flash("Rule deleted.", "info")
        return redirect(url_for('manage_rules'))

    @app.route('/admin/rules/test_alert', methods=['POST'])
    def test_alert():
        if not current_user.role == 'Admin' and current_user.role != 'Management':
            return jsonify({'status': 'error', 'message': 'Access Denied'}), 403

        test_type = request.form.get('test_type')
        target_user_id = request.form.get('target_user')

        if test_type == 'mortality':
            title = "SLH-OP: [TEST] Mortality"
            body = "VA2: Mortality exceeded 0.05% (TEST)"
        elif test_type == 'bodyweight':
            title = "SLH-OP: [TEST] Weight"
            body = "VA2: Week 47 weights updated (TEST)"
        else:
            return jsonify({'status': 'error', 'message': 'Invalid test type'}), 400

        query = PushSubscription.query
        if target_user_id and target_user_id != 'all':
            try:
                target_id = int(target_user_id)
                query = query.filter_by(user_id=target_id)
            except ValueError:
                pass

        subscriptions = query.all()
        successful_users = set()
        failed_count = 0

        unique_user_ids = list(set([sub.user_id for sub in subscriptions]))

        # Optimize N+1 Query: Bulk fetch instead of individual gets
        users = User.query.filter(User.id.in_(unique_user_ids)).all()
        user_dict = {u.id: u for u in users}

        for uid in unique_user_ids:
            user = user_dict.get(uid)
            if user:
                # send_push_alert returns boolean indicating if at least one sub succeeded
                success = send_push_alert(uid, title, body, transient=True)
                if success:
                    successful_users.add(user.username)
                else:
                    failed_count += 1

        return jsonify({
            'status': 'success',
            'successful_users': sorted(list(successful_users)),
            'failed_count': failed_count
        })

    @app.route('/admin/rules', methods=['GET', 'POST'])
    def manage_rules():
        if not current_user.role == 'Admin' and current_user.role != 'Management':
            flash("Access Denied.", "danger")
            return redirect(url_for('index'))

        if request.method == 'POST':
            name = request.form.get('name')
            metric = request.form.get('metric')
            operator = request.form.get('operator')
            threshold = float(request.form.get('threshold'))
            is_active = True if request.form.get('is_active') else False

            rule = NotificationRule(
                name=name,
                metric=metric,
                operator=operator,
                threshold=threshold,
                is_active=is_active
            )
            db.session.add(rule)
            safe_commit()
            flash(f"Rule '{name}' added successfully.", "success")
            return redirect(url_for('manage_rules'))

        rules = NotificationRule.query.all()

        # Get users with active subscriptions for the target user dropdown
        subbed_user_ids = db.session.query(PushSubscription.user_id).distinct().all()
        subbed_user_ids = [uid[0] for uid in subbed_user_ids]
        subscribed_users = User.query.filter(User.id.in_(subbed_user_ids)).order_by(User.username).all()

        return render_template('admin/rules_manager.html', rules=rules, subscribed_users=subscribed_users)

    @app.route('/admin/activity_log')
    def admin_activity_log():
        if not current_user.role == 'Admin':
            flash("Access Denied.", "danger")
            return redirect(url_for('index'))

        user_id = request.args.get('user_id')
        resource_type = request.args.get('resource_type')

        query = UserActivityLog.query

        if user_id:
            query = query.filter_by(user_id=user_id)
        if resource_type:
            query = query.filter_by(resource_type=resource_type)

        logs = query.order_by(UserActivityLog.timestamp.desc()).limit(200).all()
        users = User.query.order_by(User.username).all()

        # Extract unique resource types for filter dropdown
        resource_types = db.session.query(UserActivityLog.resource_type).distinct().all()
        resource_types = [r[0] for r in resource_types]

        return render_template('admin/activity_log.html', logs=logs, users=users, resource_types=resource_types)

    @app.route('/admin/audit_logs')
    @login_required
    def admin_audit_logs():
        if not current_user.role == 'Admin':
            flash("Access Denied.", "danger")
            return redirect(url_for('index'))
        logs = SystemAuditLog.query.order_by(SystemAuditLog.timestamp.desc()).all()
        return render_template('admin/audit_logs.html', logs=logs)

    @app.route('/settings', methods=['GET'])
    @login_required
    def settings():
        user_id = current_user.id
        # Fetch notification history for the user (last 30)
        notifications = NotificationHistory.query.filter_by(user_id=user_id).order_by(NotificationHistory.created_at.desc()).limit(30).all()

        # Mark as read when viewing settings
        for n in notifications:
            if not n.is_read:
                n.is_read = True
        safe_commit()

        # Pass vapid public key
        vapid_public_key = os.getenv('VAPID_PUBLIC_KEY', '')
        if not vapid_public_key:
            flash("VAPID Keys are missing. Push notifications cannot be enabled.", "warning")

        return render_template('settings.html', vapid_public_key=vapid_public_key, notifications=notifications)

    @app.route('/settings/profile_update', methods=['POST'])
    @login_required
    def profile_update():
        user = User.query.get(current_user.id)
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for('login'))

        current_password = request.form.get('current_password')
        new_name = request.form.get('name')
        new_username = request.form.get('username')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # Phase 2: Security check - Does the password match?
        if not check_password_hash(user.password_hash, current_password):
            flash("Incorrect current password. Profile update denied.", "danger")
            return redirect(url_for('settings'))

        changed = False

        if new_username and new_username != user.username:
            # Check if username already exists
            existing_user = User.query.filter_by(username=new_username).first()
            if existing_user:
                flash("Username already taken. Please choose another.", "danger")
                return redirect(url_for('settings'))
            user.username = new_username
            changed = True

        if new_name is not None and new_name != user.name:
            user.name = new_name
            changed = True

        if new_password:
            if new_password != confirm_password:
                flash("New passwords do not match.", "danger")
                return redirect(url_for('settings'))
            user.set_password(new_password)
            changed = True

        if changed:
            if safe_commit():
                session['user_name'] = user.name or user.username
                flash("Profile updated successfully.", "success")
            else:
                flash("Database error occurred while updating profile.", "danger")
        else:
            flash("No changes were made.", "info")

        return redirect(url_for('settings'))
