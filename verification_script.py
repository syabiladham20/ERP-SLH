from playwright.sync_api import sync_playwright

def verify_frontend():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 1. Visit Dashboard
        page.goto("http://localhost:5000/")
        page.screenshot(path="/home/jules/verification/01_dashboard_empty.png")
        print("Dashboard screenshot taken.")

        # 2. Go to Manage Flocks and Create a Flock
        page.click("text=Manage Flocks")
        page.fill("#house_name", "VA1")
        page.fill("#intake_date", "2023-11-01")
        page.fill("#intake_male", "5000")
        page.fill("#intake_female", "5000")
        page.click("button:text('Create Flock')")

        # Verify success message and redirect
        page.wait_for_selector(".alert-success")
        page.screenshot(path="/home/jules/verification/02_flock_created.png")
        print("Flock created screenshot taken.")

        # 3. Go to Daily Entry
        page.click("text=Daily Entry")

        # Verify VA1 is selectable
        # Check if the select option with text VA1 exists

        page.select_option("#house_id", label="VA1")
        page.fill("input[name='mortality_male']", "10")
        page.fill("input[name='feed_male_gp_bird']", "150")
        page.fill("input[name='water_reading_1']", "10000")
        page.fill("input[name='water_reading_2']", "10200")
        page.fill("input[name='water_reading_3']", "10500")
        page.click("button:text('Submit Log')")

        # Verify success
        page.wait_for_selector(".alert-success")
        page.screenshot(path="/home/jules/verification/03_log_submitted.png")
        print("Log submitted screenshot taken.")

        browser.close()

if __name__ == "__main__":
    verify_frontend()
