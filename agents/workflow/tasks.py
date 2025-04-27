import json
from pathlib import Path
from typing import Optional, Dict, List
import re

from bs4 import BeautifulSoup
from google.genai import types, errors as google_errors  # type: ignore
from prefect import task, get_run_logger

# Assuming site_utils will be refactored as planned
from agents.site_utils import extract_publication_date, extract_pdf_meta_with_gemini, _pdf_site_path
# Assuming puppet script remains available
from agents.puppet.puppeteer import take_screenshot
from .feedback import task_run_feedback_loop  # import:keep
from .model import client, PRIMARY_MODEL, FALLBACK_MODEL


# --- Constants (Consider moving to config.py later) ---

_PROMPT = f"""
<p>I'd like you to translate the core ideas of the provided academic paper into an interactive website, drawing
    inspiration from the explanatory style of Bret Victor or Bartosz Ciechanowski (<a
        href="https://ciechanow.ski/">https://ciechanow.ski/</a>).</p>
<p>The goal is a single HTML file (with Javascript and CSS inlined) that serves as a professional, well-decorated, and
    highly intuitive blog post exploring the paper's main concepts. A layman with a high school education in
    mathematics and should be able to build understanding of the paper's mathematical model and contributions mainly
    through interacting with javascript simulations and visualizations.</p>
<p><strong>Requirements:</strong></p>
<ol>
    <li>
        <p><strong>Technical:</strong></p>
        <ul>
            <li>Use simulation when appropriate. Use interaction to demonstrate the mathematical concepts and build
                intuition for the ideas. Every visualization should always have some interactive component, always
                preferred over static charts.</li>
            <li>Prioritize <strong>interactive Javascript visualizations</strong> to build intuition <em>before</em>
                introducing complex equations.</li>
            <li>If you must make a chart, prefer using D3.js.</li>
            <li>Use <strong>MathJax</strong> to render ALL mathematical notation.
            </li>
            <li>For any custom diagrams or simple simulations needed beyond standard charts, use <strong>plain
                    Javascript</strong> or <strong>p5.js</strong> if appropriate.</li>
        </ul>
    </li>
    <li>
        <p><strong>Content Flow &amp; Explanation:</strong></p>
        <ul>
            <li>Start with a clear, high-level introduction to the problem the paper addresses.</li>
            <li>Gradually build up the necessary concepts. <strong>Define terms of art clearly</strong> and provide
                Wikipedia links where helpful (e.g.,
                <code>&lt;a href=&quot;WIKI_URL&quot; target=&quot;_blank&quot;&gt;Term&lt;/a&gt;</code>).</li>
            <li>Focus on the <strong>core mathematical model or central idea</strong> of the paper. Don't try to
                cover everything; aim for depth on the key concept.</li>
        </ul>
    </li>
    <li>
        <p><strong>Handling Mathematical Models:</strong></p>
        <ul>
            <li>When appropriate, write a Monte Carlo simulation which explores how the modeled system might evolve.
            </li>
            <li>When the paper presents constrained optimization models, create interactive visualizations that allow
                users to adjust key input parameters (e.g., costs, resource limits, demand levels) via sliders or input
                fields.</li>
            <li>Make visualizations genuinely interactive: use sliders for parameters, tooltips on hover for data
                points, potentially buttons to trigger calculation updates or simulation steps.</li>
            <li>Use many small visualizations of ideas to build up intuition, rather than just relying on one or two.
            </li>
        </ul>
    </li>
    <li>
        <p><strong>Output Format &amp; Quality:</strong></p>
        <ul>
            <li>Produce a <strong>single, self-contained HTML file</strong>.</li>
            <li>Include <strong>comments in the Javascript code</strong> explaining the logic, especially for
                visualizations and interactive elements.</li>
            <li>Ensure the final output is polished, professional, and technically accurate according to the paper's
                content.</li>
            <li>You'll probably need to generate the HTML body first before adding scripts and styles at the bottom,
                given your autoregressive generation of the page. </li>
        </ul>
    </li>
</ol>
<p>Please generate the HTML file based on the provided paper content and these instructions.</p>
""".strip()


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

@task(retries=2, retry_delay_seconds=5)
def task_generate_initial_html(pdf_path: Path, papername: str) -> str:
    """
    Generates the initial HTML site explanation from a PDF using Gemini.
    """
    logger = get_run_logger()
    logger.info(f"Starting initial HTML generation for {papername} from {pdf_path}")

    try:
        # Ensure client() is available and working
        gemini_client = client()
        if not gemini_client:
            raise ConnectionError("Failed to initialize Gemini client.")

        logger.info(f"Uploading PDF: {pdf_path}")
        files = [
            gemini_client.files.upload(file=str(pdf_path)),
        ]
        logger.info(f"PDF uploaded successfully: {files[0].uri}")

    except Exception as e:
        logger.error(f"Failed to upload PDF {pdf_path}: {e}")
        raise  # Re-raise after logging

    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_uri(
                    file_uri=files[0].uri,
                    mime_type=files[0].mime_type,
                ),
                types.Part.from_text(text=_PROMPT),
            ],
        ),
    ]
    generate_content_config = types.GenerateContentConfig(
        temperature=0.7,
        response_mime_type="text/plain",
    )

    model_to_use = PRIMARY_MODEL
    try:
        logger.info(f"Generating content with primary model: {model_to_use}")
        chunks = gemini_client.models.generate_content_stream(
            model=model_to_use,
            contents=contents,
            config=generate_content_config,
        )
        # Use tqdm for progress if desired, but might clutter Prefect logs
        # result = "".join(chunk.text for chunk in tqdm(chunks, desc=f"Generating with {model_to_use}"))
        result = "".join(chunk.text for chunk in chunks)
        logger.info(f"Successfully generated content with {model_to_use}")
        # Clean up uploaded file
        gemini_client.files.delete(name=files[0].name)
        logger.info(f"Deleted uploaded file: {files[0].name}")
        return _parse_html(result)

    except google_errors.ClientError as e:
        logger.warning(f"Resource exhausted for primary model ({model_to_use}): {e}. Falling back...")
        model_to_use = FALLBACK_MODEL
        try:
            logger.info(f"Attempting generation with fallback model: {model_to_use}")
            chunks = gemini_client.models.generate_content_stream(
                model=model_to_use,
                contents=contents,
                config=generate_content_config,
            )
            result = "".join(chunk.text for chunk in chunks)
            logger.info(f"Successfully generated content with fallback {model_to_use}")
            return _parse_html(result)
        except Exception as fallback_e:
            logger.error(f"Generation failed with fallback model ({model_to_use}) as well: {fallback_e}")
            raise
        finally:
            try:
                # Clean up uploaded file
                gemini_client.files.delete(name=files[0].name)
                logger.info(f"Deleted uploaded file: {files[0].name}")
            except Exception as delete_e:
                logger.error(f"Failed to delete uploaded file after fallback failure: {delete_e}")

    except Exception as primary_e:
        logger.error(f"An unexpected error occurred with the primary model ({model_to_use}): {primary_e}")
         # Clean up uploaded file even on failure
        try:
            gemini_client.files.delete(name=files[0].name)
            logger.info(f"Deleted uploaded file after primary failure: {files[0].name}")
        except Exception as delete_e:
            logger.error(f"Failed to delete uploaded file after primary failure: {delete_e}")
        raise primary_e # Re-raise other unexpected exceptions


@task(retries=2, retry_delay_seconds=5)
def task_fix_links(initial_html: str, papername: str) -> str:
    """
    Uses Gemini with Google Search to fix broken Wikipedia links and
    convert any remaining markdown to HTML tags.
    """
    logger = get_run_logger()
    logger.info(f"Starting link fixing for {papername}")

    try:
        gemini_client = client()
        if not gemini_client:
            raise ConnectionError("Failed to initialize Gemini client.")

        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=f"""
Please use the google search tool to fix any broken links to wikipedia in this html:

```html
{initial_html}
```

The wikipedia links in the corrected HTML should point to the real articles in wikipedia.

Also, any text which is accidentally using **markdown** should use <strong>html tags</strong> instead.

Return only the complete, corrected HTML content within a ```html``` block.
""")
                ]
            )
        ]
        # Use a fast model suitable for tool use
        model = "gemini-2.5-flash-preview-04-17"
        tools = [
            types.Tool(google_search=types.GoogleSearch())
        ]
        generate_content_config = types.GenerateContentConfig(
            temperature=0,
            tools=tools,
            response_mime_type="text/plain", # Expecting text containing the HTML block
        )

        logger.info(f"Calling Gemini ({model}) with search tool to fix links...")
        chunks = gemini_client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=generate_content_config,
        )
        result = "".join(chunk.text for chunk in chunks)
        logger.info(f"Successfully received response for link fixing.")

        fixed_html = _parse_html(result)
        # Basic check to see if parsing likely succeeded
        if not fixed_html.strip().startswith('<'):
             logger.warning(f"Link fixing parsing might have failed for {papername}. Result snippet: {fixed_html[:100]}")
             # Decide whether to return original or potentially broken result
             # Returning the potentially broken one allows feedback loop to try fixing it
             # return initial_html
        return fixed_html

    except Exception as e:
        logger.error(f"An error occurred during link fixing for {papername}: {e}")
        # Return the original HTML if fixing fails
        return initial_html


@task
def task_save_final_html(final_html: str, papername: str) -> Path:
    """
    Saves the final refined HTML content to the designated file path.
    Returns the path to the saved file.
    """
    logger = get_run_logger()
    logger.info(f"Saving final HTML for {papername}")

    # Define output directory and ensure it exists
    project_root = Path(__file__).parent.parent
    output_dir = project_root / "static" / "sites"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{papername}.html"

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_html)
        logger.info(f"Final HTML successfully saved to: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Failed to save final HTML for {papername} to {output_path}: {e}")
        raise # Re-raise the exception to fail the task


@task(retries=1, retry_delay_seconds=10) # Give screenshot a bit more time/retries
async def task_take_screenshot(final_html_path: Path, papername: str) -> Path:
    """
    Takes a screenshot of the final generated HTML site using Puppeteer.
    Returns the path to the saved screenshot.
    """
    logger = get_run_logger()
    logger.info(f"Taking final screenshot for {papername} from {final_html_path}")

    # Define screenshot directory and ensure it exists
    project_root = Path(__file__).parent.parent
    screenshot_dir = project_root / "static" / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    # Construct the relative URL path expected by the screenshot tool
    # Assumes the web server root corresponds to the project root or 'static' dir
    relative_site_url = f"/static/sites/{final_html_path.name}"
    final_screenshot_path = screenshot_dir / f"{papername}.png" # Expected final path

    try:
        # The take_screenshot function might return the actual path it saved to
        # We pass the papername as the base name and the desired output directory
        saved_path_str = await take_screenshot(
            url=relative_site_url,
            name=papername,
            output_dir=screenshot_dir
        )
        # Ensure the returned path is a Path object
        saved_path = Path(saved_path_str) if saved_path_str else final_screenshot_path

        if saved_path.exists():
             logger.info(f"Final screenshot successfully saved to: {saved_path}")
             return saved_path
        else:
             # This case might happen if take_screenshot fails silently or returns None/empty
             logger.error(f"take_screenshot reported success but file not found at {saved_path}")
             raise FileNotFoundError(f"Screenshot file not found after take_screenshot call: {saved_path}")

    except Exception as e:
        logger.error(f"Failed to take final screenshot for {papername}: {e}")
        raise # Re-raise the exception to fail the task


@task
def task_extract_metadata(final_html: str, pdf_path: Path, papername: str) -> Dict[str, any]:
    """
    Extracts metadata from the final HTML content and the original PDF.
    Consolidates logic previously in site_utils.create_site_entry.
    """
    logger = get_run_logger()
    logger.info(f"Extracting metadata for {papername}")

    metadata = {"paper": papername}

    # 1. Extract HTML Title
    try:
        soup = BeautifulSoup(final_html, "html.parser")
        h1 = soup.find("h1")
        if not h1:
            logger.warning(f"No h1 element found in HTML for {papername}, using papername as title.")
            metadata["title"] = papername.replace("_", " ").title() # Fallback title
        else:
            metadata["title"] = h1.get_text().strip()
            logger.info(f"Extracted HTML title: {metadata['title']}")
    except Exception as e:
        logger.error(f"Error extracting HTML title for {papername}: {e}")
        metadata["title"] = papername.replace("_", " ").title() # Fallback on error

    # 2. Extract PDF Metadata (Date, Authors, Title)
    try:
        metadata["publication_date"] = extract_publication_date(pdf_path)
        logger.info(f"Extracted publication date: {metadata['publication_date']}")
    except Exception as e:
        logger.error(f"Error extracting publication date for {pdf_path}: {e}")
        metadata["publication_date"] = "" # Default on error

    try:
        pdf_meta = extract_pdf_meta_with_gemini(pdf_path)
        metadata["authors"] = pdf_meta.authors
        metadata["pdf_title"] = pdf_meta.title
        logger.info(f"Extracted PDF authors: {metadata['authors']}")
        logger.info(f"Extracted PDF title: {metadata['pdf_title']}")
    except Exception as e:
        logger.error(f"Error extracting PDF authors/title for {pdf_path} using Gemini: {e}")
        metadata["authors"] = ["Unknown Author"] # Default on error
        metadata["pdf_title"] = "Unknown Title" # Default on error

    # 3. Determine Relative Paths
    metadata["path"] = f"/sites/{papername}.html" # HTML path relative to static dir
    try:
        metadata["pdf_site"] = _pdf_site_path(pdf_path) # PDF path relative to papers dir
        logger.info(f"Determined PDF site path: {metadata['pdf_site']}")
    except ValueError as e:
         logger.error(f"Error determining PDF site path for {pdf_path}: {e}")
         metadata["pdf_site"] = "" # Default on error

    logger.info(f"Metadata extraction complete for {papername}")
    return metadata


@task
def task_update_index(new_metadata_list: List[Dict[str, any]]):
    """
    Updates the sites index file (src/lib/sites.json) with new or updated
    metadata entries from the current flow run.
    """
    logger = get_run_logger()
    logger.info(f"Updating sites index with {len(new_metadata_list)} entries.")

    project_root = Path(__file__).parent.parent
    index_path = project_root / "src/lib/sites.json"

    # Load existing sites
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            sites_list = json.load(f)
        logger.info(f"Loaded {len(sites_list)} existing entries from {index_path}")
    except FileNotFoundError:
        logger.warning(f"Sites index file not found at {index_path}. Creating a new one.")
        sites_list = []
    except json.JSONDecodeError as e:
         logger.error(f"Error decoding JSON from {index_path}: {e}. Starting with an empty list.")
         sites_list = []

    # Convert list to dict for easier updates
    sites_dict = {entry["paper"]: entry for entry in sites_list}

    # Update dict with new metadata
    updated_count = 0
    added_count = 0
    for new_entry in new_metadata_list:
        papername = new_entry.get("paper")
        if not papername:
            logger.warning("Skipping metadata entry with missing 'paper' key.")
            continue

        # Add generated timestamp (can be done here or in extract_metadata)
        # import datetime # Add this import at the top if not already present
        # new_entry["generated"] = datetime.datetime.now().isoformat()

        if papername in sites_dict:
            updated_count += 1
            sites_dict[papername].update(new_entry) # Update existing entry
        else:
            added_count += 1
            sites_dict[papername] = new_entry # Add new entry

    logger.info(f"Index update summary: {added_count} added, {updated_count} updated.")

    # Convert back to list and sort
    final_sites_list = list(sites_dict.values())
    final_sites_list.sort(key=lambda x: x.get('paper', '')) # Sort by paper name

    # Write updated index back to file
    try:
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(final_sites_list, f, indent=2)
        logger.info(f"Successfully wrote {len(final_sites_list)} entries to {index_path}")
    except Exception as e:
        logger.error(f"Failed to write updated sites index to {index_path}: {e}")
        raise # Re-raise to fail the task
