from playwright.sync_api import sync_playwright

def verify_labels():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Use context to store login state
        context = browser.new_context()
        page = context.new_page()

        # Login
        page.goto("http://127.0.0.1:5000/login")
        # Ensure we are really logged in
        page.fill('input[name="username"]', 'admin')
        page.fill('input[name="password"]', 'admin')
        page.click('button[type="submit"]')
        page.wait_for_timeout(2000)

        # Navigate to Executive Dashboard Performance Charts tab
        page.goto("http://127.0.0.1:5000/executive/flock/1")
        page.click('button[data-bs-target="#charts"]')

        # Take a screenshot
        page.wait_for_timeout(2000)
        page.screenshot(path="/home/jules/verification/verification_2.png", full_page=True)

        browser.close()

if __name__ == "__main__":
    verify_labels()
