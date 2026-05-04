import os
import sys
from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader('app/templates'))

# Register dummy filters so compilation doesn't fail on them
env.filters['date_fmt'] = lambda x: x
env.filters['basename'] = lambda x: x

def check_template(filename):
    try:
        env.get_template(filename)
        return True
    except Exception as e:
        print(f"Error compiling {filename}: {e}")
        return False

success = True
for root, dirs, files in os.walk('app/templates'):
    for file in files:
        if file.endswith('.html'):
            rel_path = os.path.relpath(os.path.join(root, file), 'app/templates')
            if not check_template(rel_path):
                success = False

if not success:
    sys.exit(1)
else:
    print("All templates compiled successfully!")
