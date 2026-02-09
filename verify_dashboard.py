from app import app, db, House, Flock, DailyLog, ChartConfiguration
import json
from datetime import date

def test_api():
    client = app.test_client()

    with app.app_context():
        # Setup Data
        house = House.query.first()
        if not house:
            house = House(name='TestHouse')
            db.session.add(house)
            db.session.commit()

        flock = Flock.query.filter_by(house_id=house.id).first()
        if not flock:
            flock = Flock(house_id=house.id, batch_id='TestBatch', intake_date=date.today())
            db.session.add(flock)
            db.session.commit()

        log = DailyLog(flock_id=flock.id, date=date.today(), eggs_collected=1000, cull_eggs_crack=10)
        db.session.add(log)
        db.session.commit()

        # Test 1: Metrics List
        res = client.get('/api/metrics')
        print(f"Metrics: {res.status_code}")
        metrics = json.loads(res.data)
        assert 'mortality_female_pct' in metrics

        # Test 2: Custom Data
        res = client.post(f'/api/flock/{flock.id}/custom_data', json={
            'metrics': ['eggs_collected', 'cull_eggs_crack_pct']
        })
        print(f"Custom Data: {res.status_code}")
        data = json.loads(res.data)
        assert len(data['eggs_collected']) > 0
        assert data['cull_eggs_crack_pct'][0] == 1.0 # 10/1000 * 100

        # Test 3: Save Chart
        res = client.post(f'/api/house/{house.id}/charts', json={
            'title': 'Test Chart',
            'chart_type': 'line',
            'config': {'metrics': ['eggs_collected']},
            'is_template': True
        })
        print(f"Save Chart: {res.status_code}")

        # Test 4: Get Config
        res = client.get(f'/api/house/{house.id}/dashboard_config')
        print(f"Get Config: {res.status_code}")
        config = json.loads(res.data)
        assert len(config['charts']) > 0
        assert config['charts'][0]['title'] == 'Test Chart'

        # Test 5: Templates
        res = client.get('/api/templates')
        print(f"Templates: {res.status_code}")
        temps = json.loads(res.data)
        assert len(temps) > 0

        # Cleanup (optional, but good practice if repeatable)
        # ChartConfiguration.query.delete()
        # db.session.commit()

    print("ALL TESTS PASSED")

if __name__ == "__main__":
    test_api()
