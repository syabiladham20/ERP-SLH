import re

with open('app.py', 'r') as f:
    content = f.read()

# Define the helper function near the db initialization
helper_code = """
db = SQLAlchemy(app)
migrate = Migrate(app, db)

def safe_commit():
    try:
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Database transaction failed: {e}")
        flash("A database error occurred. Your changes have been rolled back to prevent data corruption.", "danger")
        return False

"""

content = content.replace("db = SQLAlchemy(app)\nmigrate = Migrate(app, db)", helper_code)

# Now find all `db.session.commit()` calls and replace them with `safe_commit()`
# except the ones already in a try-except block that explicitly handles it.
# Wait, some places actually use try-except and db.session.rollback() explicitly already.
# I will do a global replace, and fix double rollbacks if they exist.
# Or better, just replace db.session.commit() with safe_commit() everywhere.

content = re.sub(r'\bdb\.session\.commit\(\)', 'safe_commit()', content)

with open('app.py', 'w') as f:
    f.write(content)
