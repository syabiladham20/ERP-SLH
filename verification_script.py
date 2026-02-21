from playwright.sync_api import sync_playwright
import time

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Login
        print("Logging in...")
        page.goto("http://localhost:5000/login")
        page.fill("input[name='username']", "admin")
        page.fill("input[name='password']", "admin123")
        page.click("button[type='submit']")

        # Go to Executive Flock Detail
        print("Navigating to flock detail...")
        page.goto("http://localhost:5000/executive/flock/1")

        # Screenshot debug
        page.screenshot(path="debug_page.png")

        # Click "Performance Charts" tab
        try:
            print("Clicking charts tab...")
            page.click("#charts-tab", timeout=5000)
            time.sleep(2) # Wait for chart render

            # Screenshot
            page.screenshot(path="verification_flock_detail.png", full_page=True)
            print("Screenshot saved to verification_flock_detail.png")
        except Exception as e:
            print(f"Error: {e}")
            page.screenshot(path="error_page.png")

        browser.close()

if __name__ == "__main__":
    run()
