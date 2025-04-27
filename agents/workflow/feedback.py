import time
import re
import asyncio
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from prefect import task, get_run_logger
from google.genai import types

from agents.puppet.puppeteer import take_screenshot
from .model import client, FALLBACK_MODEL

# --- Constants ---

_FEEDBACK_PROMPT = """
Review the following HTML content for an interactive website based on an academic paper.
Ensure it meets the requirements outlined previously (interactive visualizations, MathJax, D3/p5.js where appropriate, clear explanations, single file).
If improvements are needed, provide the complete, updated HTML content within a ```html``` block.
If the HTML looks good and meets all requirements, respond with the exact string "looks good".

HTML to review:
```html
{html_content}
```
"""

_HTML_RE = re.compile(
    r'```html\s+(.*?)\s+```',  # Non-greedy match with whitespace handling
    re.DOTALL | re.IGNORECASE  # Allow multiline and case variations
)


@task(retries=1, retry_delay_seconds=5) # Fewer retries for the loop itself
def task_run_feedback_loop(fixed_html: str, papername: str, max_iterations: int = 6) -> str:
    """
    Runs an iterative feedback loop with Gemini to refine HTML content,
    taking screenshots at each iteration.
    """
    ctx = _setup_feedback_loop(papername)

    current_html_content = fixed_html
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        ctx.logger.info(f"Feedback loop iteration {iteration}/{max_iterations} for {papername}...")

        try:
            gemini_client = client()
            if not gemini_client:
                raise ConnectionError("Failed to initialize Gemini client.")

            screenshot_file = asyncio.run(ctx.take_and_upload_screenshot(
                gemini_client, papername, iteration, current_html_content
            ))

            feedback_response = ctx.call_gemini_feedback(
                gemini_client, current_html_content, screenshot_file
            )

            updated_html = ctx.process_feedback_response(feedback_response)
            if not updated_html:
                ctx.logger.info(f"Feedback loop completed for {papername} after {iteration} iterations.")
                break # Exit loop

            current_html_content = updated_html

        except Exception as e:
            ctx.logger.error(f"Error during feedback loop iteration {iteration} for {papername}: {e}")
            break

    if iteration >= max_iterations:
        ctx.logger.warning(f"Feedback loop for {papername} reached max iterations ({max_iterations}) without completion.")

    return current_html_content


_PROJECT_ROOT = Path(__file__).parent.parent.parent # Need to go up two levels from agents/workflow


@dataclass
class Feedbackctx:
    """ctx object for the feedback loop."""
    logger: object # Prefect logger type is not strictly defined, use object
    screenshot_dir: Path

    async def take_and_upload_screenshot(self, gemini_client, papername: str, iteration: int, current_html_content: str):
        """
        Saves intermediate HTML, takes a screenshot, and uploads it to Gemini.
        Returns the uploaded file object or None on failure.
        """
        # under static, this will make the site available at 'https://localhost:5173/sites-wip/<sitename>'
        iter_name = f"{papername}_feedback_iter{iteration}"
        temp_html_path = _PROJECT_ROOT / "static" / "sites-wip" / f"{iter_name}.html"
        screenshot_path = self.screenshot_dir / f"{iter_name}.png"
        self.logger.info(f"Saving intermediate HTML for screenshot: {temp_html_path}")
        temp_html_path.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_html_path, "w", encoding="utf-8") as f:
            f.write(current_html_content)

        screenshot_file = None
        try:
            self.logger.info(f"Taking intermediate screenshot: {screenshot_path}")
            relative_temp_html_url = f"https://localhost:5173/sites-wip/{temp_html_path.name}"
            time.sleep(0.5) # Need the vite server to load it
            await take_screenshot(relative_temp_html_url, iter_name, output_dir=self.screenshot_dir) # Use await here
            self.logger.info(f"Intermediate screenshot saved: {screenshot_path}")

            # Upload screenshot to Gemini
            self.logger.info(f"Uploading screenshot: {screenshot_path}")
            screenshot_file = gemini_client.files.upload(file=str(screenshot_path))
            self.logger.info(f"Screenshot uploaded successfully: {screenshot_file.uri}")

        except Exception as screen_e:
            self.logger.error(f"Failed to take or upload intermediate screenshot for {papername} iteration {iteration}: {screen_e}")
        finally:
            # Clean up temporary HTML file
            if temp_html_path.exists():
                temp_html_path.unlink()
                self.logger.info(f"Deleted temporary HTML file: {temp_html_path}")

        return screenshot_file

    def call_gemini_feedback(self, gemini_client, current_html_content: str, screenshot_file: Optional[types.File]) -> str:
        """
        Prepares content, calls Gemini API for feedback, and cleans up the uploaded file.
        Returns the raw response text.
        """
        # Prepare content for feedback model
        feedback_parts = [
            types.Part.from_text(text=_FEEDBACK_PROMPT.format(html_content=current_html_content)),
        ]
        if screenshot_file:
             feedback_parts.append(
                 types.Part.from_uri(
                     file_uri=screenshot_file.uri,
                     mime_type=screenshot_file.mime_type,
                 )
             )

        feedback_contents = [
            types.Content(
                role="user",
                parts=feedback_parts,
            ),
        ]

        feedback_generate_config = types.GenerateContentConfig(
            temperature=0.05, # Low temperature for stability
            response_mime_type="text/plain",
        )

        self.logger.info(f"Calling Gemini ({FALLBACK_MODEL}) for feedback...")
        feedback_chunks = gemini_client.models.generate_content_stream(
            model=FALLBACK_MODEL, # Using fallback model for stability/cost
            contents=feedback_contents,
            config=feedback_generate_config,
        )
        feedback_response = "".join(chunk.text for chunk in feedback_chunks)

        # Clean up uploaded screenshot file
        if screenshot_file:
            try:
                gemini_client.files.delete(name=screenshot_file.name)
                self.logger.info(f"Deleted uploaded screenshot file: {screenshot_file.name}")
            except Exception as delete_e:
                self.logger.error(f"Failed to delete uploaded screenshot file: {delete_e}")

        return feedback_response

    def process_feedback_response(self, feedback_response: str) -> Optional[str]:
        """
        Checks if the feedback response indicates completion and parses the HTML if not.
        Returns a tuple: (is_complete, updated_html).
        """
        # Parse and update HTML
        try:
            self.logger.info("Parsing feedback response...")
            updated_html = self._parse_html(feedback_response)
            self.logger.info("HTML updated based on feedback.")
            return updated_html
        except ValueError:
            if len(feedback_response) < 20:
                trimmed_response = feedback_response
            else:
                trimmed_response = feedback_response[:20] + '...<snip>'
            self.logger.info("Found no HTML; assuming it looks good. (response=%s)" % trimmed_response)
            return None

    def _parse_html(self, output: str) -> str:
        """Extract HTML content from markdown code block."""
        match: Optional[re.Match[str]] = _HTML_RE.search(output)
        if not match or not match.group(1):
            raise ValueError("Failed to extract HTML block.")
        return match.group(1).strip()


def _setup_feedback_loop(papername: str) -> Feedbackctx:
    """
    Sets up the logger and screenshot directory for the feedback loop.
    Returns a Feedbackctx object.
    """
    logger = get_run_logger()
    logger.info(f"Starting feedback loop for {papername}")

    # Define screenshot directory and ensure it exists
    # Assuming project root is parent of 'agents'
    screenshot_dir = _PROJECT_ROOT / "static" / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    return Feedbackctx(logger=logger, screenshot_dir=screenshot_dir)








