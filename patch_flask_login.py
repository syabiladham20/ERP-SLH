import re

with open('app.py', 'r') as f:
    content = f.read()

# 1. Imports
content = re.sub(r'from flask_login import current_user',
                 'from flask_login import current_user, LoginManager, login_user, logout_user, login_required, UserMixin',
                 content)

# 2. Add LoginManager setup after app initialization
login_manager_code = """
app = Flask(__name__)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Please log in to continue."
login_manager.login_message_category = "info"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
"""
content = content.replace('app = Flask(__name__)', login_manager_code)

# 3. Add UserMixin to User model
content = content.replace('class User(db.Model):', 'class User(db.Model, UserMixin):')

with open('app.py', 'w') as f:
    f.write(content)
