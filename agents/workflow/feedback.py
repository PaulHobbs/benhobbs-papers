import re
from pathlib import Path
from typing import Optional

from prefect import task, get_run_logger
from google.genai import types

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


@task(retries=1, retry_delay_seconds=5) # Fewer retries for the loop itself
async def task_run_feedback_loop(fixed_html: str, papername: str, max_iterations: int = 5) -> str:
    """
    Runs an iterative feedback loop with Gemini to refine HTML content,
    taking screenshots at each iteration.
    """
    logger, screenshot_dir = _setup_feedback_loop(papername)

    current_html_content = fixed_html
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        logger.info(f"Feedback loop iteration {iteration}/{max_iterations} for {papername}...")

        try:
            gemini_client = client()
            if not gemini_client:
                raise ConnectionError("Failed to initialize Gemini client.")

            screenshot_file = await _take_and_upload_screenshot(
                gemini_client, papername, iteration, screenshot_dir, current_html_content, logger
            )

            # Call Gemini for feedback
            feedback_response = _call_gemini_feedback(
                gemini_client, current_html_content, screenshot_file, logger
            )

            # Process feedback response
            is_complete, updated_html = _process_feedback_response(feedback_response, logger)

            if is_complete:
                logger.info(f"Feedback loop completed for {papername} after {iteration} iterations.")
                break # Exit loop

            current_html_content = updated_html

        except Exception as e:
            logger.error(f"Error during feedback loop iteration {iteration} for {papername}: {e}")
            # Decide how to handle errors - break the loop for now
            break

    if iteration >= max_iterations:
        logger.warning(f"Feedback loop for {papername} reached max iterations ({max_iterations}) without completion.")

    return current_html_content


_PROJECT_ROOT = Path(__file__).parent.parent.parent # Need to go up two levels from agents/workflow
def _setup_feedback_loop(papername: str):
    """
    Sets up the logger and screenshot directory for the feedback loop.
    """
    logger = get_run_logger()
    logger.info(f"Starting feedback loop for {papername}")

    # Define screenshot directory and ensure it exists
    # Assuming project root is parent of 'agents'
    screenshot_dir = _PROJECT_ROOT / "static" / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    return logger, screenshot_dir


async def _take_and_upload_screenshot(gemini_client, papername: str, iteration: int, screenshot_dir: Path, current_html_content: str, logger):
    """
    Saves intermediate HTML, takes a screenshot, and uploads it to Gemini.
    Returns the uploaded file object or None on failure.
    """
    temp_html_path = _PROJECT_ROOT / "sites-wip" / f"{papername}_feedback_iter{iteration}.html"
    screenshot_path = screenshot_dir / f"{papername}_feedback_iter{iteration}.png"
    logger.info(f"Saving intermediate HTML for screenshot: {temp_html_path}")
    with open(temp_html_path, "w", encoding="utf-8") as f:
        f.write(current_html_content)

    screenshot_file = None
    try:
        logger.info(f"Taking intermediate screenshot: {screenshot_path}")
        relative_temp_html_url = f"https://localhost:5173/sites-wip/{temp_html_path.name}"
        screenshot_iter_name = f"{papername}_feedback_iter{iteration}"
        await take_screenshot(relative_temp_html_url, screenshot_iter_name, output_dir=screenshot_dir) # Use await here
        logger.info(f"Intermediate screenshot saved: {screenshot_path}")

        # Upload screenshot to Gemini
        logger.info(f"Uploading screenshot: {screenshot_path}")
        screenshot_file = gemini_client.files.upload(file=str(screenshot_path))
        logger.info(f"Screenshot uploaded successfully: {screenshot_file.uri}")

    except Exception as screen_e:
        logger.error(f"Failed to take or upload intermediate screenshot for {papername} iteration {iteration}: {screen_e}")
    finally:
        # Clean up temporary HTML file
        if temp_html_path.exists():
            temp_html_path.unlink()
            logger.info(f"Deleted temporary HTML file: {temp_html_path}")

    return screenshot_file


def _call_gemini_feedback(gemini_client, current_html_content: str, screenshot_file: Optional[types.File], logger) -> str:
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

    logger.info(f"Calling Gemini ({_FALLBACK_MODEL}) for feedback...")
    feedback_chunks = gemini_client.models.generate_content_stream(
        model=_FALLBACK_MODEL, # Using fallback model for stability/cost
        contents=feedback_contents,
        config=feedback_generate_config,
    )
    feedback_response = "".join(chunk.text for chunk in feedback_chunks)

    # Clean up uploaded screenshot file
    if screenshot_file:
        try:
            gemini_client.files.delete(name=screenshot_file.name)
            logger.info(f"Deleted uploaded screenshot file: {screenshot_file.name}")
        except Exception as delete_e:
            logger.error(f"Failed to delete uploaded screenshot file: {delete_e}")

    return feedback_response


def _process_feedback_response(feedback_response: str, logger) -> tuple[bool, Optional[str]]:
    """
    Checks if the feedback response indicates completion and parses the HTML if not.
    Returns a tuple: (is_complete, updated_html).
    """
    # Check if Gemini indicates completion
    if feedback_response.strip().lower() == "looks good":
        logger.info("Gemini indicated 'looks good'. Feedback loop complete.")
        return True, None

    # Parse and update HTML
    logger.info("Parsing feedback response...")
    updated_html = _parse_html(feedback_response)
    logger.info("HTML updated based on feedback.")
    return False, updated_html


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
