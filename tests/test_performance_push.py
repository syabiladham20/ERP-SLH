import unittest
import sys
import os
import importlib.util
import time
from datetime import date
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

spec = importlib.util.spec_from_file_location('main_app', os.path.join(os.path.dirname(__file__), '..', 'run.py'))
main_app = importlib.util.module_from_spec(spec)
sys.modules['main_app'] = main_app
spec.loader.exec_module(main_app)

app = main_app.create_app()
from app.database import db
from app.models.models import PushSubscription, User, Farm

class PushPerformanceTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['RATELIMIT_ENABLED'] = False
        from app.extensions import limiter
        limiter.enabled = False

        self.app = app.test_client()
        self.ctx = app.app_context()
        self.ctx.push()

        db.create_all()

        unique_id = uuid.uuid4().hex[:8]
        # Create users
        for i in range(100):
            u = User(username=f'user{i}_{unique_id}', dept='Farm', role='Management')
            u.set_password('pass')
            db.session.add(u)
        db.session.commit()

        users = User.query.all()
        for u in users:
            # 5 subscriptions per user
            for j in range(5):
                sub = PushSubscription(user_id=u.id, subscription_json='{"endpoint": "https://test.local"}')
                db.session.add(sub)
        db.session.commit()

        admin_user = User(username='admin_test', dept='Farm', role='Admin')
        admin_user.set_password('pass')
        db.session.add(admin_user)
        db.session.commit()

        self.app.post('/login', data={'username': 'admin_test', 'password': 'pass'})

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_push_performance(self):
        start_time = time.time()
        for _ in range(10):
            # Using the correct endpoint `/admin/rules/test_alert`
            response = self.app.post('/admin/rules/test_alert', data={'test_type': 'mortality', 'target_user': 'all'})
        end_time = time.time()
        print(f"Push Performance Time: {end_time - start_time} seconds")
        self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
