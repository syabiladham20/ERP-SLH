import requests
import time

BASE_URL = "http://127.0.0.1:5001"
LOGIN_URL = f"{BASE_URL}/login"
DASHBOARD_URL = f"{BASE_URL}/executive_dashboard"
USERNAME = "manager" # Management role
PASSWORD = "manager123"

def measure_dashboard():
    session = requests.Session()

    # Login
    resp = session.post(LOGIN_URL, data={"username": USERNAME, "password": PASSWORD})
    if resp.url != f"{BASE_URL}/executive_dashboard":
        print("Login Failed")
        return None

    start_time = time.time()
    resp = session.get(DASHBOARD_URL)
    end_time = time.time()

    duration = end_time - start_time
    print(f"Executive Dashboard Load Time: {duration:.3f}s")
    return duration

if __name__ == "__main__":
    measure_dashboard()
