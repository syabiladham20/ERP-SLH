import requests
import threading
import time
import random
from datetime import date, timedelta

# Configuration
BASE_URL = "http://127.0.0.1:5001"
LOGIN_URL = f"{BASE_URL}/login"
LOG_URL = f"{BASE_URL}/daily_log"
USERNAME = "farm_user"
PASSWORD = "farm123"
NUM_USERS = 10
SIMULATION_DATE = date.today().strftime('%Y-%m-%d')

results = {
    "success": 0,
    "failure": 0,
    "times": []
}

def simulate_user(user_id):
    session = requests.Session()

    # 1. Login
    try:
        t_start = time.time()
        login_payload = {
            "username": USERNAME,
            "password": PASSWORD
        }
        resp = session.post(LOGIN_URL, data=login_payload)
        if resp.url != f"{BASE_URL}/":
            print(f"User {user_id}: Login Failed (Redirected to {resp.url})")
            results["failure"] += 1
            return

        # 2. POST Data
        # We need a house ID. I'll pick a random house from 1 to 30 created earlier.
        house_id = random.randint(1, 30)

        # Ensure date is unique per user to avoid conflict if logic prevents overwrites?
        # App logic: if existing_log: log = existing_log (Update).
        # So no conflict error, just update.

        payload = {
            "house_id": house_id,
            "date": SIMULATION_DATE,
            "mortality_male": random.randint(0, 5),
            "mortality_female": random.randint(0, 5),
            "eggs_collected": random.randint(5000, 9000),
            "feed_male_gp_bird": 120,
            "feed_female_gp_bird": 160,
            "water_reading_1": random.randint(1000, 2000),
            # Add other fields as needed for completeness, but this should suffice to trigger logic
        }

        post_start = time.time()
        resp = session.post(LOG_URL, data=payload)
        post_end = time.time()

        duration = post_end - post_start
        results["times"].append(duration)

        if resp.status_code == 200 and "Daily Log" in resp.text: # Flash message usually contains "Daily Log"
             print(f"User {user_id}: Success ({duration:.3f}s)")
             results["success"] += 1
        else:
             print(f"User {user_id}: Failed Status {resp.status_code}")
             # print(resp.text[:200]) # Debug
             results["failure"] += 1

    except Exception as e:
        print(f"User {user_id}: Exception {e}")
        results["failure"] += 1

def run_test():
    print(f"Starting Stress Test with {NUM_USERS} concurrent users...")
    threads = []

    start_time = time.time()

    for i in range(NUM_USERS):
        t = threading.Thread(target=simulate_user, args=(i+1,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    end_time = time.time()
    total_time = end_time - start_time

    print("\n--- Results ---")
    print(f"Total Time: {total_time:.2f}s")
    print(f"Success: {results['success']}")
    print(f"Failure: {results['failure']}")
    if results['times']:
        avg_time = sum(results['times']) / len(results['times'])
        max_time = max(results['times'])
        min_time = min(results['times'])
        print(f"Avg Response Time: {avg_time:.3f}s")
        print(f"Max Response Time: {max_time:.3f}s")
        print(f"Min Response Time: {min_time:.3f}s")

if __name__ == "__main__":
    # Wait for server to be ready?
    # I'll manually run this script after starting server.
    run_test()
