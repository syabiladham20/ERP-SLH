from playwright.sync_api import sync_playwright, expect
import os

def test_frontend_features():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
<<<<<<< HEAD
<<<<<<< HEAD

        # 1. Create Flock with Production Start Date
        page.goto("http://127.0.0.1:5000/flocks")
        expect(page.get_by_role("heading", name="Manage Flocks")).to_be_visible()

        # Use a unique name
        page.fill('input[name="house_name"]', "TestHouseFrontend_Final")
        page.fill('input[name="intake_date"]', "2025-01-01")

=======
=======
>>>>>>> origin/import-logic-fix-704397853420473837

        # 1. Create Flock with Production Start Date
        page.goto("http://127.0.0.1:5000/flocks")
        expect(page.get_by_role("heading", name="Manage Flocks")).to_be_visible()

        # Use a unique name
        page.fill('input[name="house_name"]', "TestHouseFrontend_Final")
        page.fill('input[name="intake_date"]', "2025-01-01")

<<<<<<< HEAD
=======
=======

        # 1. Create Flock with Production Start Date
        page.goto("http://127.0.0.1:5000/flocks")
        expect(page.get_by_role("heading", name="Manage Flocks")).to_be_visible()

        # Use a unique name
        page.fill('input[name="house_name"]', "TestHouseFrontend_Final")
        page.fill('input[name="intake_date"]', "2025-01-01")

>>>>>>> origin/import-logic-fix-704397853420473837
>>>>>>> origin/import-logic-fix-704397853420473837
        # Verify New Field Exists
        prod_start_input = page.locator('input[name="production_start_date"]')
        expect(prod_start_input).to_be_visible()
        prod_start_input.fill("2025-06-01")
<<<<<<< HEAD
<<<<<<< HEAD

        # Click and wait for navigation
        with page.expect_navigation():
            page.click('button[type="submit"]')

        # Verify Success - Check URL or Element
        print(f"Current URL: {page.url}")

        # 2. Check Daily Log Form for New Fields
        page.goto("http://127.0.0.1:5000/daily_log")

        # Select House
        if page.locator('select[name="house_id"]').is_visible():
            page.select_option('select[name="house_id"]', label="TestHouseFrontend_Final")

=======
=======
>>>>>>> origin/import-logic-fix-704397853420473837

        # Click and wait for navigation
        with page.expect_navigation():
            page.click('button[type="submit"]')

        # Verify Success - Check URL or Element
        print(f"Current URL: {page.url}")

        # 2. Check Daily Log Form for New Fields
        page.goto("http://127.0.0.1:5000/daily_log")

        # Select House
        if page.locator('select[name="house_id"]').is_visible():
            page.select_option('select[name="house_id"]', label="TestHouseFrontend_Final")

<<<<<<< HEAD
=======
=======

        # Click and wait for navigation
        with page.expect_navigation():
            page.click('button[type="submit"]')

        # Verify Success - Check URL or Element
        print(f"Current URL: {page.url}")

        # 2. Check Daily Log Form for New Fields
        page.goto("http://127.0.0.1:5000/daily_log")

        # Select House
        if page.locator('select[name="house_id"]').is_visible():
            page.select_option('select[name="house_id"]', label="TestHouseFrontend_Final")

>>>>>>> origin/import-logic-fix-704397853420473837
>>>>>>> origin/import-logic-fix-704397853420473837
        # Verify "Male Hospital" section
        # Use a more generic locator if text matching is strict
        hosp_header = page.locator("h5", has_text="Male Hospital")
        expect(hosp_header).to_be_visible()
<<<<<<< HEAD
<<<<<<< HEAD

        # Screenshot
        os.makedirs("/home/jules/verification", exist_ok=True)
        page.screenshot(path="/home/jules/verification/frontend_verified.png", full_page=True)

=======
=======
>>>>>>> origin/import-logic-fix-704397853420473837

        # Screenshot
        os.makedirs("/home/jules/verification", exist_ok=True)
        page.screenshot(path="/home/jules/verification/frontend_verified.png", full_page=True)

<<<<<<< HEAD
=======
=======

        # Screenshot
        os.makedirs("/home/jules/verification", exist_ok=True)
        page.screenshot(path="/home/jules/verification/frontend_verified.png", full_page=True)

>>>>>>> origin/import-logic-fix-704397853420473837
>>>>>>> origin/import-logic-fix-704397853420473837
        browser.close()

if __name__ == "__main__":
    test_frontend_features()
