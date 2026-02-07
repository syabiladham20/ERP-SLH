import unittest
from datetime import date, timedelta
from app import app, db, Flock, Hatchability, House

class HatchabilityTestCase(unittest.TestCase):
    def setUp(self):
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['TESTING'] = True
        self.app = app.test_client()
        with app.app_context():
            db.create_all()

            # Setup data
            h = House(name="TestHouse")
            db.session.add(h)
            db.session.commit()

            f = Flock(house_id=h.id, batch_id="TestBatch", intake_date=date.today() - timedelta(days=50))
            db.session.add(f)
            db.session.commit()
            self.flock_id = f.id

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def test_hatchability_calculations(self):
        with app.app_context():
            h = Hatchability(
                flock_id=self.flock_id,
                setting_date=date.today(),
                egg_set=1000,
                clear_eggs=50,
                rotten_eggs=50,
                hatched_chicks=800
            )
            db.session.add(h)
            db.session.commit()

            # Verify calculations
            self.assertEqual(h.fertile_eggs, 900) # 1000 - 50 - 50
            self.assertAlmostEqual(h.hatch_of_total_pct, 80.0) # 800 / 1000
            self.assertAlmostEqual(h.hatch_of_fertile_pct, 88.888888, places=5) # 800 / 900

    def test_routes(self):
        # Test Add
        response = self.app.post(f'/flock/{self.flock_id}/hatchability', data={
            'setting_date': '2023-01-01',
            'egg_set': '1000'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Hatchability setting record added.', response.data)

        with app.app_context():
            h = Hatchability.query.first()
            self.assertIsNotNone(h)
            self.assertEqual(h.egg_set, 1000)
            # Check auto dates
            self.assertEqual(h.candling_date, date(2023, 1, 19)) # +18
            self.assertEqual(h.hatching_date, date(2023, 1, 22)) # +21

        # Test Update
        with app.app_context():
            h_id = Hatchability.query.first().id

        response = self.app.post(f'/hatchability/{h_id}/update', data={
            'clear_eggs': '100',
            'rotten_eggs': '50',
            'hatched_chicks': '700'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        with app.app_context():
            h = Hatchability.query.get(h_id)
            self.assertEqual(h.clear_eggs, 100)
            self.assertEqual(h.fertile_eggs, 850) # 1000 - 100 - 50

if __name__ == '__main__':
    unittest.main()
