import dataclasses
from pyppeteer import launch
from pathlib import Path


@dataclasses.dataclass(frozen=True)
class Log:
    level: str
    msg: str

    def __str__(self):
        return f'{self.level}: {self.msg}'


@dataclasses.dataclass
class Result:
    screenshot_path: str
    logs: list[Log]



async def take_screenshot(url: str, name: str, output_dir: str = None) -> Result:
    """
    Takes a screenshot of the given URL and saves it based on the site name.

    Args:
        url: The URL to navigate to.
        name: The name of the site, used for the screenshot filename.
        output_dir: optionally, a directory to output screenshots in. Otherwise,
            will output into $repo_root/static/sites/screenshots.
    """
    result = Result()
    browser = await launch(headless=True, defaultViewport=None, args=['--no-sandbox']) # Use headless=True for server environments, add --no-sandbox for potential container environments
    page = await browser.newPage()
    def onLog(level, msg):
        print(f'Browser {level}: {msg}')
        result.logs.append(Log(level, msg))

    page.on('console', lambda msg: onLog('info', msg))
    page.on('pageerror', lambda msg: onLog('error', msg))

    try:
        await page.goto(url, {
            'waitUntil': 'networkidle2',
            'timeout': 60000 # Increase timeout to 60 seconds
        })
        await page.waitFor(500); # Wait a bit more for rendering

        # Ensure the screenshots directory exists
        screenshot_dir = output_dir or Path(__file__).parent.parent.parent / "static" / "sites" / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        screenshot_path = screenshot_dir / f"{name}.png"
        result.screenshot_path = screenshot_path
        await page.screenshot({'path': str(screenshot_path), 'fullPage': True})
        print(f"Screenshot saved to {screenshot_path}")

    except Exception as e:
        print(f"Error taking screenshot for {url}: {e}")
    finally:
        await browser.close()

    return result

