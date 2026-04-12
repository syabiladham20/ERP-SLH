from playwright.sync_api import sync_playwright

def verify_delete_button():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Navigate to home
        page.goto("http://127.0.0.1:5000/")

        # 1. Dashboard: Verify NO delete button on active flock card
        # We need an active flock. If none, we create one.
        if "No active flocks" in page.content():
            print("No active flocks, creating one...")
            page.click("text=Create one now")
            page.fill("#house_name", "TestHousePlaywright")
            page.fill("#intake_date", "2023-11-20")
            page.click("text=Create Flock")
            page.goto("http://127.0.0.1:5000/")

        # Check for Delete button on Dashboard
        print("Checking Dashboard for Delete button...")
        # We look for a form with delete action or button text 'Delete'
        # But 'Delete' button might exist in other places (e.g. Nav? No).
        # Specifically inside .card-footer

        delete_btns = page.locator(".card-footer button:has-text('Delete')")
        if delete_btns.count() > 0:
             print(f"FAIL: {delete_btns.count()} Delete button(s) found on Dashboard!")
        else:
             print("PASS: No Delete button on Dashboard.")

        page.screenshot(path="dashboard_verification.png")

        # 2. Manage Flocks: Verify logic
        print("Checking Manage Flocks...")

        # Create an Inactive Flock to verify it HAS delete button.
        # Create another active flock first, then close it.
        page.click("text=Manage Flocks")
        page.fill("#house_name", "InactiveHouse")
        page.fill("#intake_date", "2023-11-21")
        page.click("text=Create Flock")

        # Now close it. Go to Dashboard.
        page.goto("http://127.0.0.1:5000/")

        # Handle confirmation dialog
        page.on("dialog", lambda dialog: dialog.accept())

        # Find the card for InactiveHouse and click Close
        card = page.locator(".card").filter(has_text="InactiveHouse")
        if card.count() > 0:
            card.locator("button:has-text('Close')").click()
            # Wait for navigation/reload
            page.wait_for_load_state("networkidle")
        else:
            print("Error: Could not find InactiveHouse card")

        # Now go back to Manage Flocks
        page.click("text=Manage Flocks")

        # Take screenshot of Manage Flocks
        page.screenshot(path="manage_flocks_verification.png")

        # Verify:
        # "InactiveHouse" row -> Has Delete
        # We can look for the row
        row = page.locator("tr").filter(has_text="InactiveHouse")
        if row.locator("button:has-text('Delete')").count() > 0:
             print("PASS: Delete button found for Inactive flock.")
        else:
             print("FAIL: Delete button NOT found for Inactive flock.")

        # "TestHousePlaywright" row -> No Delete
        row_active = page.locator("tr").filter(has_text="TestHousePlaywright")
        if row_active.locator("button:has-text('Delete')").count() == 0:
             print("PASS: Delete button NOT found for Active flock.")
        else:
             print("FAIL: Delete button found for Active flock!")

        browser.close()

if __name__ == "__main__":
    verify_delete_button()
