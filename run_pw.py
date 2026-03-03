from playwright.sync_api import Page, expect, sync_playwright

def test_vaccine_schedule(page: Page):
    page.goto("http://localhost:5000/login")
    page.fill("input[name='username']", "admin")
    page.fill("input[name='password']", "admin123")
    page.click("button[type='submit']")

    page.wait_for_selector("text=Upcoming Vaccine Schedule")

    page.screenshot(path="dashboard.png")

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            test_vaccine_schedule(page)
        finally:
            browser.close()
