from playwright.sync_api import sync_playwright

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.on("console", lambda msg: print(f"Console {msg.type}: {msg.text}"))

        page.goto("http://127.0.0.1:5000/login")
        page.fill("input[name='username']", "admin")
        page.fill("input[name='password']", "admin123")
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")

        page.goto("http://127.0.0.1:5000/flock/1")
        page.wait_for_load_state("networkidle")
        page.click("#charts-tab")
        page.wait_for_timeout(1000)

        page.evaluate("""
            () => {
                const canvas = document.getElementById('generalChart');
                const chart = Chart.getChart(canvas);

                const dsIndex = chart.data.datasets.findIndex(ds => ds.label === 'Clinical Notes');
                if (dsIndex >= 0) {
                    const ds = chart.data.datasets[dsIndex];
                    const ptIndex = ds.data.findIndex(p => p !== null && p.note);
                    if (ptIndex >= 0) {
                        const meta = chart.getDatasetMeta(dsIndex);
                        const pt = meta.data[ptIndex];
                        const rect = canvas.getBoundingClientRect();

                        console.log("Is dataset hidden?", ds.hidden);

                        // Let's forcefully dispatch a click and ensure intersection logic works
                        const ev = new MouseEvent('click', {
                            clientX: rect.left + pt.x,
                            clientY: rect.top + pt.y,
                            bubbles: true
                        });
                        canvas.dispatchEvent(ev);
                        console.log("Triggered natural click");
                    }
                }
            }
        """)

        page.wait_for_timeout(2000)
        page.screenshot(path="verification_modal_natural2.png")
        browser.close()

if __name__ == "__main__":
    main()
