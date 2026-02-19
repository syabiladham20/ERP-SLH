import unittest
from app import app, db, Standard

class StandardsTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        self.app = app.test_client()
        self.ctx = app.app_context()
        self.ctx.push()
        db.create_all()

        # Login as Farm Admin
        with self.app.session_transaction() as sess:
            sess['user_dept'] = 'Farm'
            sess['user_role'] = 'Admin'
            sess['is_admin'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_add_standard_with_new_fields(self):
        response = self.app.post('/standards', data={
            'action': 'add',
            'week': '10',
            'std_mortality_male': '0.5',
            'std_mortality_female': '0.4',
            'std_bw_male': '1000',
            'std_bw_female': '900',
            'std_egg_prod': '85.5',
            'std_egg_weight': '60.5',
            'std_hatchability': '90.2'
        }, follow_redirects=True)

        self.assertIn(b'Standard added', response.data)

        s = Standard.query.filter_by(week=10).first()
        self.assertIsNotNone(s)
        self.assertEqual(s.std_egg_weight, 60.5)
        self.assertEqual(s.std_hatchability, 90.2)
        self.assertEqual(s.std_egg_prod, 85.5)

    def test_add_standard_defaults(self):
        # Test defaults if fields are missing/empty
        response = self.app.post('/standards', data={
            'action': 'add',
            'week': '11'
        }, follow_redirects=True)

        s = Standard.query.filter_by(week=11).first()
        self.assertEqual(s.std_egg_weight, 0.0)
        self.assertEqual(s.std_hatchability, 0.0)

if __name__ == '__main__':
    unittest.main()
