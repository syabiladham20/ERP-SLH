import pytest
from playwright.sync_api import Page, expect

def test_charts_page_debug(page: Page, server_url):
    page.on("console", lambda msg: print(f"Browser Console: {msg.text}"))
    page.on("pageerror", lambda err: print(f"Browser Error: {err}"))

    # 1. Login
    page.goto(f"{server_url}/login")
    page.fill('input[name="username"]', 'admin')
    page.fill('input[name="password"]', 'admin')
    page.click('button[type="submit"]')
    page.wait_for_url(f"{server_url}/")

    # 2. Go to flock detail charts
    # Assuming test flock is id 1
    page.goto(f"{server_url}/flock/1")

    # Wait for charts to render
    page.wait_for_selector("#chartsWrapper")
    page.wait_for_timeout(2000)

    # Click charts tab if it exists
    charts_tab = page.query_selector("#charts-tab")
    if charts_tab:
        charts_tab.click()
        page.wait_for_timeout(1000)

    # Scroll down to hatching chart
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(1000)

    # Click weekly
    page.click("label[for='modeWeeklyHatching']")
    page.wait_for_timeout(1000)

    print("Test finished successfully.")
