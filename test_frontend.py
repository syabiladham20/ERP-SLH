from playwright.sync_api import sync_playwright

def test_frontend():
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

if __name__ == "__main__":
    test_frontend()
