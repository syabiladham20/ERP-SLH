import sys
import os

# Add the parent directory to sys.path so we can import 'app'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.main import app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
