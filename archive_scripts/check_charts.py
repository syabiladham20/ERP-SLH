import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        errors = []
        page.on("pageerror", lambda err: errors.append(f"Page Error: {err}"))
        page.on("console", lambda msg: errors.append(f"Console {msg.type}: {msg.text}") if msg.type == "error" else None)

        print("Checking farm view...")
        await page.goto("http://127.0.0.1:5000/login")
        await page.fill("input[name='username']", "admin")
        await page.fill("input[name='password']", "admin123")
        await page.click("button[type='submit']")

        await page.goto("http://127.0.0.1:5000/flock/1")
        await asyncio.sleep(2)

        print("Farm View Errors:")
        for err in errors:
            print(err)

        errors.clear()

        print("Checking executive view...")
        await page.goto("http://127.0.0.1:5000/executive/flock/1")
        await asyncio.sleep(2)

        print("Executive View Errors:")
        for err in errors:
            print(err)

        await browser.close()

asyncio.run(run())
