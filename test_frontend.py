from playwright.sync_api import sync_playwright
import subprocess
import sys
import time
import os

os.environ['PYTHONPATH'] = '/app'

def test_frontend():
    print("Testing original frontend...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Go to login
        page.goto("http://localhost:5000/login")
        page.fill("input[name='username']", "admin")
        page.fill("input[name='password']", "admin123")
        page.click("button[type='submit']")
        page.wait_for_load_state('networkidle')

        # Go to flock 1 detail
        page.goto("http://localhost:5000/flock/1")
        page.wait_for_load_state('networkidle')

        # Take a screenshot of the flock page
        page.screenshot(path="flock_detail_verification_final.png", full_page=True)

        browser.close()

def test_login_logo_and_offline_mirror():
    print("Testing login logo and offline mirror fallback...")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto('http://127.0.0.1:5000/login')

            page.wait_for_load_state("networkidle")

            svg_element = page.locator('svg.slh-rooster-outline.text-primary')
            assert svg_element.is_visible(), "New rooster SVG logo should be visible on the login page."

            login_container = page.locator('.page-center .container')
            old_svg = login_container.locator('#slh-logo-static')
            assert old_svg.count() == 0, "Old static logo should be removed from the login screen."

            print("Login logo test passed.")

            context = browser.new_context()
            page2 = context.new_page()
            page2.goto('http://127.0.0.1:5000/login')
            page2.evaluate('localStorage.setItem("slh_offline_user_id", "test-user-id")')
            page2.goto('http://127.0.0.1:5000/offline_mirror')

            page2.wait_for_load_state("domcontentloaded")
            time.sleep(1) # wait for the script to execute and populate UI

            error_msg = page2.locator('text=User not authenticated. Cannot access local cache.')
            assert not error_msg.is_visible(), "The page should have fallen back to localStorage and NOT shown the unauthenticated error."

            no_data_msg = page2.locator('text=No Offline Data')
            assert no_data_msg.is_visible(), "The page should attempt to load data for the fallback user_id and find none."

            print("Offline cache fallback test passed.")

            context.close()
            browser.close()

    except Exception as e:
        print(f"Error: {e}")
        raise

if __name__ == "__main__":
    proc = subprocess.Popen([sys.executable, 'app.py'], cwd='/app')
    time.sleep(3) # Wait for server to start
    try:
        test_frontend()
        test_login_logo_and_offline_mirror()
    finally:
        proc.terminate()
        proc.wait()
