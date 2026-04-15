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
from app.models.models import House, Flock, Medication, User, Farm

class MedicationPerformanceTestCase(unittest.TestCase):
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

        farm = Farm.query.filter_by(name='Test Farm').first()
        if not farm:
            farm = Farm(name='Test Farm')
            db.session.add(farm)
            db.session.commit()

        unique_id = uuid.uuid4().hex[:8]
        # Create some dummy data
        for i in range(100):
            h = House(name=f'House{i}_{unique_id}')
            db.session.add(h)
        db.session.commit()

        houses = House.query.all()
        for i, h in enumerate(houses):
            f = Flock(flock_id=f'F{i}_{unique_id}', farm_id=farm.id, house_id=h.id, intake_date=date(2023, 1, 1), intake_male=100, intake_female=100)
            db.session.add(f)
        db.session.commit()

        flocks = Flock.query.all()
        for f in flocks:
            for j in range(5):
                m = Medication(flock_id=f.id, drug_name=f'Drug{j}', dosage='10mg', start_date=date(2023, 1, 1))
                db.session.add(m)
        db.session.commit()

        if not User.query.filter_by(username='admin_test').first():
            u = User(username='admin_test', dept='Farm', role='Admin')
            u.set_password('pass')
            db.session.add(u)
            db.session.commit()

        self.app.post('/login', data={'username': 'admin_test', 'password': 'pass'})

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_medication_performance(self):
        start_time = time.time()
        for _ in range(10):
            response = self.app.get('/health_log/medication')
        end_time = time.time()
        print(f"Improved Time: {end_time - start_time} seconds")
        self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
