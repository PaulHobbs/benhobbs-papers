import json
from pathlib import Path
from typing import Optional, Dict, List
import re

from bs4 import BeautifulSoup
from google.genai import types # type: ignore
from prefect import task, get_run_logger

from agents.site_utils import extract_publication_date, extract_pdf_meta_with_gemini, _pdf_site_path
from .feedback import task_run_feedback_loop  # import:keep
from .model import client, generate_content_with_attachment, PRIMARY_MODEL, FALLBACK_MODEL, WEAKER_MODEL


# --- Constants (Consider moving to config.py later) ---

_PROMPT = """
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
<example>
  Here is an example simulation you could use in your post:

  ---
  {sim}
  ---
</example>
<p>Please generate the HTML file based on the provided paper content and these instructions.</p>
""".strip()


_HTML_RE = re.compile(
    r'```html\s+(.*?)\s+```',  # Non-greedy match with whitespace handling
    re.DOTALL | re.IGNORECASE  # Allow multiline and case variations
)

# --- Prefect Tasks ---

from prefect.cache_policies import FLOW_PARAMETERS

@task()
def task_initial_sim(pdf_path: Path, papername: str) -> str:
    """
    Focuses on a single, nice simulation for the paper
    """
    gemini_client = client()
    file = gemini_client.files.upload(file=str(pdf_path))
    contents = [types.Content(
        role="user",
        parts=[
            types.Part.from_uri(file_uri=file.uri, mime_type=file.mime_type),
            types.Part.from_text(text="""
Please make an interesting interactive javascript simulation using monte carlo which
demonstrates the key dynamic in the model or models in this paper.

Make it as a fully-fledged, detailed and as complete as possible. This should be
the capstone demonstration of what this paper is about, which could be used as a
key element of discussion in an educational blog post about the paper's ideas.

Ideally the simulation should inspire learning through play, and should be fun
to just toy around with. This requires it to have a certain amount of depth and
emergent complexity as a result of the model's dynamics showing through the
observables. The user should be able to make some gestalt mental connection to
the model's fundamental dynamics by just playing around with it for a while.
""".strip()),
        ],
    )]

    response = generate_content_with_attachment(
        gemini_client,
        contents=contents,
        generate_content_config=types.GenerateContentConfig(
            temperature=0.7,
            response_mime_type="text/plain",
        ),
        primary_model=PRIMARY_MODEL,
        fallback_model=FALLBACK_MODEL,
        uploaded_file_name=file.name
    )

    # Parse ```...``` blocks so we can get rid of the greetings etc
    return '\n\n'.join(
        f'```{block}```'
        for block in parse_codeblocks(response)
    )


@task(cache_policy=FLOW_PARAMETERS)
def task_generate_initial_html(pdf_path: Path, papername: str) -> str:
    """
    Generates the initial HTML site explanation from a PDF using Gemini.
    """
    logger = get_run_logger()
    logger.info(f"Starting initial HTML generation for {papername} from {pdf_path}")

    sim = task_initial_sim(pdf_path=pdf_path, papername=papername)

    gemini_client = client()
    file = gemini_client.files.upload(file=str(pdf_path))

    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_uri(
                    file_uri=file.uri,
                    mime_type=file.mime_type,
                ),
                types.Part.from_text(text=_PROMPT.format(sim=sim)),
            ],
        ),
    ]

    return generate_content_with_attachment(
        gemini_client,
        contents=contents,
        generate_content_config=types.GenerateContentConfig(
            temperature=0.7,
            response_mime_type="text/plain",
        ),
        primary_model=PRIMARY_MODEL,
        fallback_model=FALLBACK_MODEL,
        uploaded_file_name=file.name
    )


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
        tools = [
            types.Tool(google_search=types.GoogleSearch())
        ]
        generate_content_config = types.GenerateContentConfig(
            temperature=0,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            tools=tools,
            response_mime_type="text/plain", # Expecting text containing the HTML block
        )

        logger.info(f"Calling Gemini ({WEAKER_MODEL}) with search tool to fix links...")
        chunks = gemini_client.models.generate_content_stream(
            model=WEAKER_MODEL,
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
    _PROJECT_ROOT = Path(__file__).parent.parent
    output_dir = _PROJECT_ROOT / "static" / "sites"
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


_PROJECT_ROOT = Path(__file__).parent.parent.parent

@task
def task_update_index(new_metadata_list: List[Dict[str, any]]):
    """
    Updates the sites index file (src/lib/sites.json) with new or updated
    metadata entries from the current flow run.
    """
    logger = get_run_logger()
    logger.info(f"Updating sites index with {len(new_metadata_list)} entries.")

    index_path = _PROJECT_ROOT / "src/lib/sites.json"

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


def _parse_html(output: str) -> str:
    """Extract HTML content from markdown code block."""
    match = _HTML_RE.search(output)
    if not match or not match.group(1):
        raise ValueError("Failed to extract HTML block.")
    return match.group(1).strip()

    
_CODEBLOCK_PATTERN = re.compile(r"```[^\n]*\n?(.*?)\n?```", re.DOTALL)
def parse_codeblocks(markdown: str) -> list[str]:
  """
  Parses a Markdown string and extracts the content of fenced code blocks.

  Args:
    markdown: The Markdown string to parse.

  Returns:
    A list of strings, where each string is the content found
    within a ```...``` code block. Leading/trailing whitespace
    within the block (like the newline after the language specifier
    or before the closing fence) is stripped. Returns an empty list
    if no code blocks are found.
  """
  # Regex explanation:
  # ```       # Match the literal opening triple backticks
  # [^\n]* # Match optional language specifier (any characters except newline)
  # \n?       # Match an optional newline immediately after the opening fence or language specifier
  # (         # Start capturing group for the code content
  #   .*?     # Match any character (including newlines due to re.DOTALL)
  #           # non-greedily (.*?) to stop at the first closing fence
  # )         # End capturing group
  # \n?       # Match an optional newline immediately before the closing fence
  # ```       # Match the literal closing triple backticks
  #
  # The re.DOTALL flag allows '.' to match newline characters, which is essential
  # for capturing multi-line code blocks.
  # re.findall returns only the captured group content.

  matches = re.findall(_CODEBLOCK_PATTERN, markdown)
  # Often, the content captured includes a leading newline (if code starts
  # on the line after ```lang) and a trailing newline (if the code ends
  # on the line before ```). We strip these for cleaner output.
  return [content.strip() for content in matches]