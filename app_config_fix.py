import os
basedir = os.path.abspath(os.path.dirname(__file__))

# Replace the existing database configuration lines with this block
database_url = os.getenv('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

# Force absolute path to instance/farm.db
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///' + os.path.join(basedir, 'instance', 'farm.db')
