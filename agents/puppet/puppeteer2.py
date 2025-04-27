#!/usr/bin/env python3
import asyncio
import sys
import time # Import time for potential debugging delays if needed
from pyppeteer import launch
from pyppeteer.errors import TimeoutError # Import TimeoutError

async def main():
    if len(sys.argv) < 2:
        print("Usage: python puppeteer2.py <URL>")
        return

    url = sys.argv[1]
    screenshot_path = 'example.png'
    # --- SELECTOR ---
    # Try 'iframe' first. If it fails, try the more specific class
    # you found: 'iframe.s-CxnggYcgLGFz'
    iframe_selector = 'iframe'
    # iframe_selector = 'iframe.s-CxnggYcgLGFz' #<- Example if you need the class

    print(f"Launching browser...")
    browser = None # Initialize browser to None for finally block
    try:
        browser = await launch(
            headless=True, # Set to False for debugging visibility
            defaultViewport=None, # We'll set viewport dynamically
            args=[
                '--start-maximized', # Helps ensure consistent width reading
                '--no-sandbox', # Often needed in containerized environments
                '--disable-setuid-sandbox'
                ]
        )
        page = await browser.newPage()
        page.on('console', lambda msg: print(f'PAGE LOG: {msg.text}'))
        page.on('pageerror', lambda err: print(f'PAGE ERR: {err}'))

        print(f"Navigating to {url}...")
        await page.goto(url, {
            'waitUntil': 'networkidle0', # Wait for network activity to cease
            'timeout': 60000 # 60 second timeout for navigation
        })
        print("Navigation complete. Waiting for dynamic content (iframe)...")
        # No fixed sleep here - let waitForSelector handle finding the iframe

        required_height = 0
        iframe_processed = False

        # --- Logic to find and measure iframe ---
        print(f"Looking for iframe with selector: '{iframe_selector}'")
        try:
            # Wait for the iframe element to appear in the main DOM.
            # Increased timeout allows more time for client-side rendering.
            iframe_element = await page.waitForSelector(
                iframe_selector,
                {'timeout': 20000} # Wait up to 20 seconds for iframe element
            )
            print("Iframe element found. Getting content frame...")
            frame = await iframe_element.contentFrame()

            if frame:
                print("Iframe content frame acquired. Waiting for iframe content body...")
                # Wait for the body element *inside* the iframe to ensure it's loaded
                await frame.waitForSelector('body', {'timeout': 30000}) # Wait up to 30s for iframe body
                print("Iframe body found. Calculating dimensions...")
                # Small delay for rendering stability AFTER frame content is found
                await asyncio.sleep(1)

                # Calculate the scroll height inside the iframe
                iframe_content_height = await frame.evaluate('() => document.body.scrollHeight')
                print(f"Iframe internal content scrollHeight: {iframe_content_height}px")

                # Get the iframe's position and size on the main page
                iframe_box = await iframe_element.boundingBox()
                if not iframe_box:
                     print("Warning: Could not get iframe bounding box. Height calculation might be less accurate.")
                     # Estimate required height based only on iframe content height if box fails
                     page_scroll_height = await page.evaluate('() => document.body.scrollHeight')
                     required_height = max(page_scroll_height, iframe_content_height) # Best guess
                else:
                    print(f"Iframe bounding box: {iframe_box}")
                    # Calculate the total height needed on the main page
                    required_height_based_on_iframe = iframe_box['y'] + iframe_content_height
                    # Also get the main page's scroll height in case other elements make it taller
                    page_scroll_height = await page.evaluate('() => document.body.scrollHeight')
                    # Use the maximum of the two calculations
                    required_height = max(page_scroll_height, required_height_based_on_iframe)
                    print(f"Main page scrollHeight: {page_scroll_height}px")
                    print(f"Required height based on iframe content: {required_height_based_on_iframe}px")

                iframe_processed = True # Mark that we successfully processed iframe sizing

            else:
                 # This case might be less likely if waitForSelector succeeded, but check anyway
                 print("Could not get iframe content frame despite finding element.")

        except TimeoutError:
            # This handles timeout from page.waitForSelector(iframe_selector, ...)
            print(f"Iframe ('{iframe_selector}') not found within timeout.")
        except Exception as e:
            # Catch other potential errors during iframe processing
            print(f"Error processing iframe: {e}")

        # --- Fallback or Final Height Calculation ---
        if not iframe_processed:
            print("Falling back to main page scrollHeight for screenshot.")
            required_height = await page.evaluate('() => document.body.scrollHeight')

        if not required_height or required_height < 500: # Basic sanity check
            print(f"Warning: Calculated height ({required_height}px) seems low. Using minimum 1080px.")
            required_height = max(required_height, 1080)


        # --- Viewport Resizing ---
        # Use documentElement.clientWidth for a more reliable render width
        current_width = await page.evaluate('() => document.documentElement.clientWidth')
        if not current_width or current_width < 800: # Fallback if evaluate fails or width is too small
             print(f"Warning: Could not get reliable clientWidth ({current_width}). Using default 1920px.")
             current_width = 1920

        print(f"Final calculated required height: {required_height}px. Resizing viewport...")

        # Add a buffer to the calculated height
        target_height = int(required_height) + 100

        await page.setViewport({
            'width': current_width,
            'height': target_height,
            # 'deviceScaleFactor': 1 # Optional: set device scale factor if needed
        })

        print(f"Viewport resized to {current_width}x{target_height}. Waiting for potential reflow...")
        # Wait after resizing allows the browser to redraw layout
        await asyncio.sleep(2)

        # --- Screenshot ---
        print(f"Taking screenshot: {screenshot_path}")
        await page.screenshot({
            'path': screenshot_path,
            'fullPage': True # This should now work correctly after the resize
        })
        print("Screenshot saved.")

    except TimeoutError as e:
        # This catches timeouts primarily from page.goto or frame.waitForSelector
        print(f"Timeout Error during navigation or critical wait: {e}")
    except Exception as e:
        print(f"An general error occurred: {e}")
        import traceback
        traceback.print_exc() # Print detailed traceback for debugging
    finally:
        print("Closing browser.")
        if browser and browser.process: # Check if browser exists and is running
            await browser.close()

if __name__ == "__main__":
    # Recommended for Python 3.7+
    asyncio.run(main())
