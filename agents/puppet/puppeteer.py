import asyncio
import time
import sys
from pyppeteer import launch
from pathlib import Path

async def take_screenshot(url: str, site_name: str):
    """
    Takes a screenshot of the given URL and saves it based on the site name.

    Args:
        url: The URL to navigate to.
        site_name: The name of the site, used for the screenshot filename.
    """
    browser = await launch(headless=True, defaultViewport=None, args=['--no-sandbox']) # Use headless=True for server environments, add --no-sandbox for potential container environments
    page = await browser.newPage()
    page.on('console', lambda msg: print(f'Browser console: {msg}'))
    page.on('pageerror', lambda err: print(f'Browser page error: {err}'))

    try:
        await page.goto(url, {
            'waitUntil': 'networkidle2',
            'timeout': 60000 # Increase timeout to 60 seconds
        })
        await page.waitFor(500); # Wait a bit more for rendering

        # Ensure the screenshots directory exists
        screenshot_dir = Path(__file__).parent.parent.parent / "static" / "sites" / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        screenshot_path = screenshot_dir / f"{site_name}.png"
        await page.screenshot({'path': str(screenshot_path), 'fullPage': True})
        print(f"Screenshot saved to {screenshot_path}")

    except Exception as e:
        print(f"Error taking screenshot for {url}: {e}")
    finally:
        await browser.close()

# Removed the direct execution part
# asyncio.get_event_loop().run_until_complete(main())
