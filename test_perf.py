import sys
import time
from app import app, db, User, Flock, InventoryItem, DailyLog, GlobalStandard, Medication

def setup_data():
    with app.app_context():
        # Setup users, standards and flock
        gs = GlobalStandard.query.first()
        if not gs:
            gs = GlobalStandard(login_required=False)
            db.session.add(gs)

        user = User.query.filter_by(username='admin').first()
        if not user:
            user = User(username='admin', dept='Farm')
            user.set_password('admin')
            user.role = 'admin'
            db.session.add(user)

        flock = Flock.query.filter_by(flock_id='TEST_FLOCK_PERF').first()
        if not flock:
            # Create a house for the flock
            from app import House

            house = House.query.first()
            if not house:
                house = House(name="Test House")
                db.session.add(house)
                db.session.commit()

            from datetime import date
            flock = Flock(house_id=house.id, flock_id='TEST_FLOCK_PERF', intake_date=date(2025, 1, 1), intake_male=100, intake_female=100)
            db.session.add(flock)
            db.session.commit()

        items = []
        # Create 50 inventory items
        for i in range(50):
            item_name = f'TestMed_{i}'
            item = InventoryItem.query.filter_by(name=item_name).first()
            if not item:
                item = InventoryItem(name=item_name, type='Medication', current_stock=1000.0, unit='g')
                db.session.add(item)
            items.append(item)

        db.session.commit()
        return flock.id, [item.id for item in items]

def run_benchmark():
    flock_id, item_ids = setup_data()

    with app.test_client() as client:
        # Turn off login requirement
        with app.app_context():
            gs = GlobalStandard.query.first()
            if gs:
                gs.login_required = False
                db.session.commit()

        # Login
        with app.app_context():
            user = User.query.filter_by(username='admin').first()
            if not user:
                user = User(username='admin', dept='Farm', role='Admin')
                user.set_password('admin')
                db.session.add(user)
                db.session.commit()

        client.post('/login', data={'username': 'admin', 'password': 'admin'})

        data = {
            'date': '2025-01-02',
            'mortality_male': 0,
            'mortality_female': 0,
            'feed_male': 10,
            'feed_female': 10,
            'water_intake': 20,
            'body_weight_male': 100,
            'body_weight_female': 100,
            'eggs_collected': 0,
        }

        for i, item_id in enumerate(item_ids):
            data.setdefault('med_drug_name[]', []).append(f'Med_{i}')
            data.setdefault('med_inventory_id[]', []).append(str(item_id))
            data.setdefault('med_dosage[]', []).append('1g')
            data.setdefault('med_amount_used[]', []).append('1g')
            data.setdefault('med_amount_qty[]', []).append('1')
            data.setdefault('med_start_date[]', []).append('2025-01-02')
            data.setdefault('med_end_date[]', []).append('2025-01-03')
            data.setdefault('med_remarks[]', []).append('None')

        # Clear existing logs for this date
        with app.app_context():
            DailyLog.query.filter_by(flock_id=flock_id, date='2025-01-02').delete()
            Medication.query.filter_by(flock_id=flock_id).delete()
            db.session.commit()

        # Warmup
        client.get('/')

        # Get house id
        with app.app_context():
            flock = Flock.query.get(flock_id)
            house_id = flock.house_id
            data['house_id'] = str(house_id)

        start_time = time.time()
        for _ in range(10):
            # we need to change date since it must be unique or delete log each time
            with app.app_context():
                DailyLog.query.filter_by(flock_id=flock_id, date='2025-01-02').delete()
                Medication.query.filter_by(flock_id=flock_id).delete()
                db.session.commit()

            response = client.post(f'/daily_log', data=data, follow_redirects=True)
            if response.status_code != 200:
                print(f"Error: Status code {response.status_code}")
                print(response.data.decode())
            assert response.status_code == 200

        end_time = time.time()
        avg_time = (end_time - start_time) / 10
        print(f"Average time for /daily_log with 50 medications: {avg_time:.4f} seconds")

if __name__ == '__main__':
    run_benchmark()
