import asyncio
import time
import sys
from pyppeteer import launch

async def main():
    browser = await launch(headless=False, defaultViewport=None)
    page = await browser.newPage()
    page.on('console', lambda msg: print(msg))
    page.on('pageerror', lambda err: print(f'err: {err}'))
    await page.goto(sys.argv[1], {
        'waitUntil': 'networkidle2',
    })
    await page.waitFor(500);
    await page.screenshot({'path': 'example.png', 'fullPage': True})
    await browser.close()

asyncio.get_event_loop().run_until_complete(main())
