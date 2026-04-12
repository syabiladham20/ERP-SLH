import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        print("Checking farm view...")
        context = await browser.new_context(viewport={'width': 1280, 'height': 4000})
        page = await context.new_page()

        await page.goto("http://127.0.0.1:5000/login")
        await page.fill("input[name='username']", "admin")
        await page.fill("input[name='password']", "admin123")
        await page.click("button[type='submit']")

        await page.goto("http://127.0.0.1:5000/flock/1#performance")
        await asyncio.sleep(2)
        await page.screenshot(path="farm_chart.png", full_page=True)

        print("Checking executive view...")
        await page.goto("http://127.0.0.1:5000/executive/flock/1#performance")
        await asyncio.sleep(2)
        await page.screenshot(path="exec_chart.png", full_page=True)

        await browser.close()

asyncio.run(run())
