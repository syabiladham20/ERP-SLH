import unittest
from datetime import date, timedelta
from app import app, db, House, Flock, DailyLog, Standard, calculate_flock_summary, GlobalStandard, enrich_flock_data

class SummaryTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        self.app = app.test_client()
        self.ctx = app.app_context()
        self.ctx.push()
        db.create_all()

        # Setup House
        h = House(name='TestHouse')
        db.session.add(h)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_calculate_flock_summary_with_null_standard(self):
        # 1. Create Flock
        flock = Flock(
            house_id=1,
            flock_id='Test_Batch1',
            intake_date=date(2023, 1, 1),
            intake_male=100,
            intake_female=100,
            phase='Production',
            production_start_date=date(2023, 2, 1), # Week 5
            start_of_lay_date=date(2023, 2, 1), # First egg also on this date
            prod_start_female=100
        )
        db.session.add(flock)

        # 2. Create Standard with NULL values
        # Week 5 (Production Week 1)
        s = Standard(
            week=5,
            production_week=1,
            std_mortality_male=0.1,
            std_mortality_female=0.1,
            std_cum_eggs_hha=None, # The culprit
            std_cum_chicks_hha=None # Also checking this
        )
        db.session.add(s)

        # 3. Create Daily Log in Production Phase
        log = DailyLog(
            flock_id=1,
            date=date(2023, 2, 2), # In Week 5
            eggs_collected=50,
            mortality_female=1
        )
        db.session.add(log)

        db.session.commit()

        # 4. Run calculation
        # We need daily_stats first
        daily_stats = enrich_flock_data(flock, [log])

        # This call should NOT raise TypeError now
        try:
            summary, table = calculate_flock_summary(flock, daily_stats)

            # Verify results
            self.assertIsNotNone(summary)
            # summary is a dict of the LATEST week.
            # production_week should be 1.
            self.assertEqual(summary['week'], 1)
            self.assertEqual(summary['hha_total_std'], 0.0) # Should default to 0
            self.assertEqual(summary['hha_chicks_std'], 0.0)

        except TypeError as e:
            self.fail(f"calculate_flock_summary raised TypeError: {e}")

if __name__ == '__main__':
    unittest.main()
