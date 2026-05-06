import re
import os
import json
import requests
from functools import wraps
from flask import request, session, flash, redirect, url_for, current_app as app
from flask_login import current_user
from werkzeug.utils import secure_filename
from pywebpush import webpush, WebPushException

from app.database import db
from app.models.models import UserActivityLog, NotificationHistory, PushSubscription, DailyLogPhoto

_ns_re = re.compile('([0-9]+)')

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower()
            for text in _ns_re.split(s)]

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
            return redirect(get_dashboard_url(current_user))

        return decorated_function
    return decorator

def round_to_whole(val):
    if val is None: return 0
    try:
        return int(float(val) + 0.5)
    except (ValueError, TypeError):
        return 0

def safe_commit():
    try:
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Database transaction failed: {e}")
        flash("A database error occurred. Your changes have been rolled back to prevent data corruption.", "danger")
        return False

def set_sqlite_pragma(dbapi_connection, connection_record):
    # Only execute PRAGMA for SQLite connections
    if type(dbapi_connection).__name__ == 'Connection' and 'sqlite3' in type(dbapi_connection).__module__:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
        except:
            pass
        cursor.close()

def log_user_activity(user_id, action, resource_type, resource_id=None, details=None):
    """
    Globally log user activities safely without interrupting the main transaction.
    """
    if not user_id:
        return
    try:
        # Wrap in a nested try-except block so if it fails, it doesn't block the caller.
        details_str = json.dumps(details) if details else None
        log = UserActivityLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            details=details_str
        )
        # Avoid flushing or committing the main transaction prematurely.
        # Just add it to the session; it will commit when the route commits.
        with db.session.no_autoflush:
            db.session.add(log)
    except Exception as e:
        app.logger.warning(f"Failed to create UserActivityLog: {e}")

def send_push_alert(user_id, title, body, url=None, transient=False):
    # Log the notification history for the user
    if not transient:
        try:
            new_notification = NotificationHistory(
                user_id=user_id,
                title=title,
                body=body,
                url=url
            )
            db.session.add(new_notification)
            safe_commit()
        except Exception as e:
            app.logger.warning(f"Failed to log notification history: {e}")
            db.session.rollback()

    vapid_private_key = os.getenv('VAPID_PRIVATE_KEY')
    vapid_claim_email = os.getenv('VAPID_CLAIM_EMAIL')

    if not vapid_private_key or not vapid_claim_email:
        app.logger.warning("VAPID keys not configured. Cannot send push notification.")
        return False

    subscriptions = PushSubscription.query.filter_by(user_id=user_id).all()
    if not subscriptions:
        return False

    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url or '/'
    })

    success_count = 0
    for sub in subscriptions:
        try:
            sub_info = json.loads(sub.subscription_json)
            webpush(
                subscription_info=sub_info,
                data=payload,
                vapid_private_key=vapid_private_key,
                vapid_claims={"sub": vapid_claim_email}
            )
            success_count += 1
        except WebPushException as ex:
            # If subscription is no longer valid, remove it
            ex_str = str(ex)
            if '403' in ex_str or '404' in ex_str or '410' in ex_str:
                app.logger.debug(f"Cleaning up invalid push subscription. Exception: {ex_str}")
                db.session.delete(sub)
                db.session.commit()
            elif hasattr(ex, 'response') and ex.response and ex.response.status_code >= 500:
                app.logger.error(f"WebPush Critical Error: {repr(ex)}")
            else:
                app.logger.error(f"WebPush Error: {repr(ex)}")
        except Exception as e:
            app.logger.error(f"Push Error: {str(e)}")

    return success_count > 0

def save_note_photos(log, note, files):
    for file in files:
        if file and file.filename != '':
            date_str = log.date.strftime('%y%m%d')
            # Ensure safe filename
            safe_orig = secure_filename(file.filename)
            raw_name = f"{log.flock.flock_id}_{date_str}_Note{note.id}_{safe_orig}"
            filename = secure_filename(raw_name)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            new_photo = DailyLogPhoto(
                log_id=log.id,
                note_id=note.id,
                file_path=filepath,
                original_filename=file.filename
            )
            db.session.add(new_photo)

def get_gemini_response(user_prompt):
    api_key = os.getenv('GEMINI_API_KEY')

    # Check if a custom model is defined, otherwise use the official gemini-1.5-pro model on v1beta
    # Ensure it's not a lite version by avoiding flash models or deprecated versions
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro-latest:generateContent?key={api_key}"

    # System context for the Poultry AI
    context = (
        "You are a Poultry Expert at Sin Long Heng Breeding Farm. "
        "Provide concise advice for Arbor Acres Plus S broiler breeders."
    )

    payload = {
        "contents": [{
            "parts": [{"text": f"{context}\n\nUser Question: {user_prompt}"}]
        }]
    }

    try:
        app.logger.info("Sending request to Gemini AI (gemini-1.5-pro)...")
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status() # Check for errors
        data = response.json()

        # Navigate the JSON structure to get the text
        reply = data['candidates'][0]['content']['parts'][0]['text']
        app.logger.info("Successfully received response from Gemini AI.")
        return reply
    except Exception as e:
        app.logger.error(f"Gemini API Error: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            app.logger.error(f"Gemini API Response: {e.response.text}")
        return f"AI Connection Error: {str(e)}"

def get_dashboard_url(user):
    if not getattr(user, 'is_authenticated', False):
        return url_for('login')
    if getattr(user, 'dept', None) == 'Hatchery':
        return url_for('hatchery_dashboard')
    elif getattr(user, 'dept', None) == 'Management':
        return url_for('executive_dashboard')
    else:
        return url_for('index')
