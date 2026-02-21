from playwright.sync_api import sync_playwright
import time

def verify_executive_dashboard():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Login
        page.goto("http://localhost:5000/login")
        page.fill("input[name='username']", "admin")
        page.fill("input[name='password']", "admin123")
        page.click("button[type='submit']")
        page.wait_for_timeout(1000) # Wait for redirect

        # Navigate to Executive Flock Detail (Flock 1)
        page.goto("http://localhost:5000/executive/flock/1")
        page.wait_for_timeout(2000) # Wait for charts to render

        # Scroll to Tabs
        page.click("#charts-tab")
        page.wait_for_timeout(1000) # Wait for tab switch

        # Scroll down to charts
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1000)

        # Take Screenshot
        page.screenshot(path="verification_flock_detail.png", full_page=True)
        print("Screenshot saved to verification_flock_detail.png")

        browser.close()

if __name__ == "__main__":
    verify_executive_dashboard()
