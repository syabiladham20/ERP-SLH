import unittest
from app import app, db, House, Flock, DailyLog, PartitionWeight, SamplingEvent
from datetime import date

class PartitionTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        self.app = app.test_client()
        self.ctx = app.app_context()
        self.ctx.push()
        db.create_all()
<<<<<<< HEAD

=======

>>>>>>> origin/import-logic-fix-704397853420473837
        # Setup House & Flock (Rearing)
        h = House(name='H1')
        db.session.add(h)
        db.session.commit()
<<<<<<< HEAD

=======

>>>>>>> origin/import-logic-fix-704397853420473837
        f = Flock(house_id=h.id, batch_id='B1', intake_date=date(2023, 1, 1), phase='Rearing')
        db.session.add(f)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_partition_submission(self):
        response = self.app.post('/daily_log', data={
            'house_id': 1,
            'date': '2023-01-02',
            # Partition Data
            'bw_F1': 100, 'uni_F1': 90,
            'bw_F2': 110, 'uni_F2': 92,
            # Male
            'bw_M1': 200, 'uni_M1': 95
        }, follow_redirects=True)
<<<<<<< HEAD

        self.assertIn(b'Daily Log submitted successfully', response.data)

        log = DailyLog.query.first()
        self.assertIsNotNone(log)

        # Check Partitions
        parts = PartitionWeight.query.filter_by(log_id=log.id).all()
        self.assertEqual(len(parts), 3) # F1, F2, M1

=======

        self.assertIn(b'Daily Log submitted successfully', response.data)

        log = DailyLog.query.first()
        self.assertIsNotNone(log)

        # Check Partitions
        parts = PartitionWeight.query.filter_by(log_id=log.id).all()
        self.assertEqual(len(parts), 3) # F1, F2, M1

>>>>>>> origin/import-logic-fix-704397853420473837
        # Check Averages
        # Female: (100+110)/2 = 105
        self.assertEqual(log.body_weight_female, 105.0)
        # Male: 200/1 = 200
        self.assertEqual(log.body_weight_male, 200.0)

    def test_partition_edit(self):
        # Create initial log via DB
        log = DailyLog(flock_id=1, date=date(2023, 1, 3))
        db.session.add(log)
        db.session.commit()
<<<<<<< HEAD

=======

>>>>>>> origin/import-logic-fix-704397853420473837
        # Edit
        response = self.app.post(f'/daily_log/{log.id}/edit', data={
            'bw_F1': 120, 'uni_F1': 80,
            'bw_M1': 220, 'uni_M1': 85
        }, follow_redirects=True)
<<<<<<< HEAD

        updated_log = DailyLog.query.get(log.id)
        self.assertEqual(updated_log.body_weight_female, 120.0)

=======

        updated_log = DailyLog.query.get(log.id)
        self.assertEqual(updated_log.body_weight_female, 120.0)

>>>>>>> origin/import-logic-fix-704397853420473837
        parts = PartitionWeight.query.filter_by(log_id=log.id).all()
        self.assertEqual(len(parts), 2)

if __name__ == '__main__':
    unittest.main()
