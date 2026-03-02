import os
import time
from app import app, db, User, Flock, DailyLog, Standard

def benchmark():
    with app.app_context():
        # Find an active flock with many logs
        flock = Flock.query.first()
        if not flock:
            print("No flocks found to benchmark.")
            return

        print(f"Benchmarking Flock {flock.id} views...")

        # We'll simulate the route's exact DB hits by importing the view function logic
        # but the easiest way is with test_client
        with app.test_client() as client:
            # Login as admin to bypass auth
            admin = User.query.filter_by(role='Admin').first()
            if admin:
                with client.session_transaction() as sess:
                    sess['user_id'] = admin.id
                    sess['is_admin'] = True
                    sess['user_role'] = 'Admin'
                    sess['user_dept'] = 'Admin'

            # Run once to warm up cache
            client.get(f'/flock/{flock.id}/spreadsheet')

            start = time.perf_counter()
            resp = client.get(f'/flock/{flock.id}/spreadsheet')
            end = time.perf_counter()

            ms1 = (end - start) * 1000
            print(f"Spreadsheet route took {ms1:.2f} ms")

            # Benchmark regular view
            start2 = time.perf_counter()
            resp2 = client.get(f'/flock/{flock.id}')
            end2 = time.perf_counter()

            ms2 = (end2 - start2) * 1000
            print(f"Flock detail view took {ms2:.2f} ms")

if __name__ == '__main__':
    benchmark()
