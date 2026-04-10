import asyncio
from playwright.async_api import async_playwright

async def verify_charts():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1280, 'height': 4000})
        page = await context.new_page()

        print("Testing modern template (Farm)...")
        await page.goto("http://127.0.0.1:5000/login")
        await page.fill("input[name='username']", "admin")
        await page.fill("input[name='password']", "admin123")
        await page.click("button[type='submit']")

        # Navigate to a flock
        # I need to check the actual url from app.py. What is the URL for the modern template?

        await browser.close()

asyncio.run(verify_charts())
