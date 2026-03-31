from playwright.sync_api import Page, expect, sync_playwright
import time

def test_admin_users_page(page: Page):
    print("Navigating to app...")
    page.goto("http://127.0.0.1:5000/login")

    print("Logging in...")
    page.fill('input[name="username"]', 'admin')
    page.fill('input[name="password"]', 'admin123')
    page.click('button[type="submit"]')

    # Wait for navigation after login
    page.wait_for_load_state('networkidle')

    print("Navigating to users management page...")
    page.goto("http://127.0.0.1:5000/admin/users")
    page.wait_for_load_state('networkidle')

    print("Taking screenshot of the users table...")
    page.screenshot(path="/tmp/users_table.png", full_page=True)

    print("Opening add user modal...")
    page.click('button:has-text("Add New User")')

    # Wait for the modal to be visible and animation to finish
    page.wait_for_selector('#addUserModal', state='visible')
    time.sleep(1) # wait for animation

    print("Taking screenshot of the add user modal...")
    page.screenshot(path="/tmp/add_user_modal.png")

    print("Verification complete.")

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            test_admin_users_page(page)
        finally:
            browser.close()
