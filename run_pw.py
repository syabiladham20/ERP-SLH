from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Increase viewport width to ensure elements have space
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto("http://localhost:5000/")
        page.goto("http://localhost:5000/flock/1")

        # Click charts tab if needed
        charts_tab = page.query_selector("#charts-tab")
        if charts_tab:
            charts_tab.click()
            page.wait_for_timeout(1000)

        page.wait_for_selector("#chartsWrapper", state="visible")

        # Take a screenshot specifically of the chart header area to see the buttons
        header = page.query_selector("#cardGeneral .card-header")
        if header:
            header.screenshot(path="screenshot_labels_btn.png")
            print("Screenshot saved to screenshot_labels_btn.png")
        else:
            print("Header not found")
        browser.close()

if __name__ == "__main__":
    run()
