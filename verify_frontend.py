import os
from playwright.sync_api import sync_playwright, expect

def verify_frontend():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Login
        page.goto("http://localhost:5000/login")
        page.fill("input[name='username']", "admin")
        page.fill("input[name='password']", "admin123")
        page.click("button[type='submit']")
        page.wait_for_load_state('networkidle')

        # 1. Farm Dashboard Flock Detail
        print("Navigating to Farm Dashboard Flock Detail...")
        page.goto("http://localhost:5000/flock/1")
        page.wait_for_load_state('networkidle')

        # Click Charts Tab
        page.click("#charts-tab")
        page.wait_for_timeout(2000) # Wait for chart to render and resize

        # Verify Date Pickers exist
        expect(page.locator("#startDateSlicer")).to_be_visible()
        expect(page.locator("#endDateSlicer")).to_be_visible()
        expect(page.locator("#dateRangeSlicer")).not_to_be_visible()

        # Take Screenshot 1
        os.makedirs("verification", exist_ok=True)
        page.screenshot(path="verification/farm_charts.png", full_page=True)
        print("Screenshot saved: verification/farm_charts.png")

        # 2. Executive Dashboard Flock Detail
        print("Navigating to Executive Dashboard Flock Detail...")
        page.goto("http://localhost:5000/executive/flock/1")
        page.wait_for_load_state('networkidle')

        # Click Charts Tab
        page.click("#charts-tab")
        page.wait_for_timeout(2000)

        # Verify Date Pickers exist
        expect(page.locator("#startDateSlicer")).to_be_visible()
        expect(page.locator("#endDateSlicer")).to_be_visible()

        # Verify "Standard Mort Limit" in legend?
        # Chart.js canvas is just a canvas. We can't easily assert internal elements with selectors.
        # Screenshot is key.

        # Take Screenshot 2
        page.screenshot(path="verification/executive_charts.png", full_page=True)
        print("Screenshot saved: verification/executive_charts.png")

        browser.close()

if __name__ == "__main__":
    verify_frontend()
