from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("console", lambda msg: print("LOG:", msg.text))
        page.goto("http://localhost:5000/login")
        page.fill("input[name='username']", "admin")
        page.fill("input[name='password']", "admin123")
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")
        page.goto("http://localhost:5000/flock/1#charts")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        page.click("#charts-tab")
        page.wait_for_timeout(500)

        page.evaluate("""() => {
            const orig = floatingNotePlugin.afterEvent;
            floatingNotePlugin.afterEvent = (chart, args) => {
                console.log('AfterEvent type:', args.event.type);
                try {
                    orig(chart, args);
                } catch(e) { console.error('Error:', e); }
            };
        }""")

        box = page.locator("#generalChart").bounding_box()
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.wait_for_timeout(500)
        browser.close()

if __name__ == "__main__":
    run()
