import asyncio
import re
from pathlib import Path
from typing import Optional, Dict, List

from google.genai import types, errors as google_errors
from prefect import task, get_run_logger

from agents.site_utils import client
from agents.puppet.puppeteer import take_screenshot
from .tasks import _FALLBACK_MODEL # Import the constant from the original file

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

# --- Helper Functions ---

def _parse_html(output: str) -> str:
    """Extract HTML content from markdown code block."""
    logger = get_run_logger()
    match: Optional[re.Match[str]] = _HTML_RE.search(output)
    if not match or not match.group(1):
        snippet = output[:200] + ('...' if len(output) > 200 else '')
        logger.error(
            f"Failed to extract HTML block. The model's response should contain:\n"
            f"1. A markdown code block wrapped in ```html\n"
            f"2. Well-formed HTML content between the markers\n"
            f"Received snippet:\n{snippet}"
        )
        # Return the original output if parsing fails, maybe feedback loop can fix it
        return output
        # Or raise ValueError("Failed to extract HTML block.") if strict parsing is required

    return match.group(1).strip()

# --- Prefect Tasks ---

@task(retries=1, retry_delay_seconds=5) # Fewer retries for the loop itself
def task_run_feedback_loop(fixed_html: str, papername: str, max_iterations: int = 5) -> str:
    """
    Runs an iterative feedback loop with Gemini to refine HTML content,
    taking screenshots at each iteration.
    """
    logger = get_run_logger()
    logger.info(f"Starting feedback loop for {papername}")

    current_html_content = fixed_html
    iteration = 0

    # Define screenshot directory and ensure it exists
    # Assuming project root is parent of 'agents'
    project_root = Path(__file__).parent.parent.parent # Need to go up two levels from agents/workflow
    screenshot_dir = project_root / "static" / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    while iteration < max_iterations:
        iteration += 1
        logger.info(f"Feedback loop iteration {iteration}/{max_iterations} for {papername}...")

        try:
            gemini_client = client()
            if not gemini_client:
                raise ConnectionError("Failed to initialize Gemini client.")

            # --- Screenshot intermediate step ---
            temp_html_path = screenshot_dir / f"{papername}_feedback_iter{iteration}.html"
            screenshot_path = screenshot_dir / f"{papername}_feedback_iter{iteration}.png"
            logger.info(f"Saving intermediate HTML for screenshot: {temp_html_path}")
            with open(temp_html_path, "w", encoding="utf-8") as f:
                f.write(current_html_content) # Use current_html_content for the screenshot

            screenshot_file = None
            try:
                logger.info(f"Taking intermediate screenshot: {screenshot_path}")
                # Use relative path for URL if take_screenshot expects it
                relative_temp_html_url = f"/static/screenshots/{temp_html_path.name}"
                # Construct a unique screenshot name for this iteration
                screenshot_iter_name = f"{papername}_feedback_iter{iteration}"
                asyncio.run(take_screenshot(relative_temp_html_url, screenshot_iter_name, output_dir=screenshot_dir))
                logger.info(f"Intermediate screenshot saved: {screenshot_path}")

                # Upload screenshot to Gemini
                logger.info(f"Uploading screenshot: {screenshot_path}")
                screenshot_file = gemini_client.files.upload(file=str(screenshot_path))
                logger.info(f"Screenshot uploaded successfully: {screenshot_file.uri}")

            except Exception as screen_e:
                logger.error(f"Failed to take or upload intermediate screenshot for {papername} iteration {iteration}: {screen_e}")
                # Continue the loop even if screenshot fails? Or raise? For now, log and continue.
                # If screenshot fails, screenshot_file will be None, and we won't add it to contents.
            finally:
                # Clean up temporary HTML file
                if temp_html_path.exists():
                    temp_html_path.unlink()
                    logger.info(f"Deleted temporary HTML file: {temp_html_path}")
            # --- End Screenshot ---

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

            logger.info(f"Calling Gemini ({_FALLBACK_MODEL}) for feedback...")
            feedback_chunks = gemini_client.models.generate_content_stream(
                model=_FALLBACK_MODEL, # Using fallback model for stability/cost
                contents=feedback_contents,
                config=feedback_generate_config,
            )
            feedback_response = "".join(chunk.text for chunk in feedback_chunks)
            # feedback_response = "".join(chunk.text for chunk in tqdm(feedback_chunks, desc=f"Feedback loop {iteration}")) # Optional tqdm

            # Clean up uploaded screenshot file
            if screenshot_file:
                try:
                    gemini_client.files.delete(name=screenshot_file.name)
                    logger.info(f"Deleted uploaded screenshot file: {screenshot_file.name}")
                except Exception as delete_e:
                    logger.error(f"Failed to delete uploaded screenshot file: {delete_e}")

            # Check if Gemini indicates completion
            if feedback_response.strip().lower() == "looks good":
                logger.info(f"Feedback loop completed for {papername} after {iteration} iterations.")
                break # Exit loop

            # Parse and update HTML
            logger.info("Parsing feedback response...")
            updated_html = _parse_html(feedback_response)

            current_html_content = updated_html
            logger.info(f"HTML updated for {papername} based on feedback iteration {iteration}.")

        except Exception as e:
            logger.error(f"Error during feedback loop iteration {iteration} for {papername}: {e}")
            # Decide how to handle errors - break the loop for now
            break

    if iteration >= max_iterations:
        logger.warning(f"Feedback loop for {papername} reached max iterations ({max_iterations}) without completion.")

    return current_html_content