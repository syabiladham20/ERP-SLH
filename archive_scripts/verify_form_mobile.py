from playwright.sync_api import sync_playwright
import time
import os

def test_mobile_form():
    with sync_playwright() as p:
        # Emulate a mobile device
        iphone_13 = p.devices['iPhone 13']
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**iphone_13)
        page = context.new_page()

        # Navigate to login (need to bypass or login to see the form)
        page.goto("http://localhost:5000/login")

        # Login
        page.fill("input[name='username']", "farm_user")
        page.fill("input[name='password']", "farm123")
        page.click("button[type='submit']")

        # Wait for redirect to index
        page.wait_for_url("http://localhost:5000/")

        # Go to daily data entry
        # Wait for the "Daily Entry" link in the navbar
        # Since it's mobile, we might need to open the navbar toggle first
        try:
            navbar_toggler = page.locator("button.navbar-toggler")
            if navbar_toggler.is_visible():
                navbar_toggler.click()
                time.sleep(1)
        except:
            pass

        # Just navigate directly to the route to be safe
        page.goto("http://localhost:5000/daily_log")

        # Wait for form to load
        page.wait_for_selector("form")

        # Scroll to Mortality section to take screenshot showing the stacked large inputs
        mortality_header = page.locator("text=Mortality & Culls (Production)")
        mortality_header.scroll_into_view_if_needed()
        time.sleep(1)

        # Take full page screenshot to see the stacking
        os.makedirs("verification", exist_ok=True)
        page.screenshot(path="verification/mobile_form_stacked.png", full_page=True)

        # Take a specific screenshot of the feed section
        feed_header = page.locator("text=Feed")
        feed_header.scroll_into_view_if_needed()
        time.sleep(1)
        page.screenshot(path="verification/mobile_form_feed.png")

        browser.close()

if __name__ == "__main__":
    # Wait for server to start
    time.sleep(3)
    test_mobile_form()
    print("Screenshots captured.")
