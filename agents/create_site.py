#!/usr/bin/env python3
import asyncio
from agents.puppet.puppeteer import take_screenshot
from site_utils import create_site_entry, client
from google.genai import types, errors  # type: ignore
from pathlib import Path
from tqdm import tqdm
from typing import Optional
import argparse
import json
import re
import sys

_PRIMARY_MODEL = "gemini-2.5-pro-exp-03-25"
_FALLBACK_MODEL = "gemini-2.5-pro-preview-03-25"
_PROMPT = f"""
<p>I&#39;d like you to translate the core ideas of the provided academic paper into an interactive website, drawing
    inspiration from the explanatory style of Bret Victor or Bartosz Ciechanowski (<a
        href="https://ciechanow.ski/">https://ciechanow.ski/</a>).</p>
<p>The goal is a single HTML file (with Javascript and CSS inlined) that serves as a professional, well-decorated, and
    highly intuitive blog post exploring the paper&#39;s main concepts. A layman with a high school education in
    mathematics and should be able to build understanding of the paper&#39;s mathematical model and contributions mainly
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
            <li>Focus on the <strong>core mathematical model or central idea</strong> of the paper. Don&#39;t try to
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
            <li>Ensure the final output is polished, professional, and technically accurate according to the paper&#39;s
                content.</li>
            <li>You&#39;ll probably need to generate the HTML body first before adding scripts and styles at the bottom,
                given your autoregressive generation of the page. </li>
        </ul>
    </li>
</ol>
<p>Please generate the HTML file based on the provided paper content and these instructions.</p>
""".strip()

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

def load_sites_index(index_path: Path) -> list:
    """Loads the sites index from sites.json."""
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            sites = json.load(f)
    except FileNotFoundError:
        sites = []
    return sites


def generate_site_html(pdf_path_str: str) -> str:
    """Generates and fixes links in the initial HTML."""
    html = generate(pdf_path_str)
    return fix_links(html)


def run_feedback_loop(output_path: Path, papername: str):
    """Runs the Gemini feedback loop for the generated HTML."""
    print(f"Starting feedback loop for {papername}")
    iteration = 0
    while True:
        iteration += 1
        print(f"Feedback loop iteration {iteration}...")

        # Read the current HTML content
        with open(output_path, "r", encoding="utf-8") as f:
            current_html_content = f.read()

        # Prepare content for feedback model
        feedback_contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=_FEEDBACK_PROMPT.format(html_content=current_html_content)),
                ],
            ),
        ]

        feedback_generate_config = types.GenerateContentConfig(
            temperature=0.05, # Low temperature for stability
            response_mime_type="text/plain",
        )

        try:
            feedback_chunks = client().models.generate_content_stream(
                model=_FALLBACK_MODEL, # Using fallback model for potentially lower cost/higher availability
                contents=feedback_contents,
                config=feedback_generate_config,
            )
            feedback_response = "".join(chunk.text for chunk in tqdm(feedback_chunks, desc=f"Feedback loop {iteration}"))

            # Check if Gemini indicates completion
            if feedback_response.strip().lower() == "looks good":
                print(f"Feedback loop completed for {papername}.")
                break # Exit loop

            # Parse and save updated HTML
            updated_html = _parse_html(feedback_response)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(updated_html)
            print(f"Updated HTML saved for {papername}.")

        except Exception as e:
            print(f"Error during feedback loop iteration {iteration} for {papername}: {e}")
            # Decide how to handle errors - for now, break the loop
            break


def update_sites_index(sites: list, new_entry: dict, index_path: Path):
    """Updates the sites list and writes it to sites.json."""
    # Remove existing entry if found, then append the new/updated one
    sites = [entry for entry in sites if entry["paper"] != new_entry["paper"]]
    sites.append(new_entry)

    # Sort sites alphabetically by paper name for consistency
    sites.sort(key=lambda x: x['paper'])

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(sites, f, indent=2)


def process_paper(pdf_path: Path, args: argparse.Namespace, sites: list, index_path: Path):
    """Processes a single paper: generates site, runs feedback, takes screenshot, updates index."""
    # Sanitize filename
    papername = pdf_path.stem.replace(" ", "_")

    # Skip if incremental flag is set and paper already exists
    if args.incremental and papername in {entry['paper'] for entry in sites}:
        print(f'Skipping {papername} (already exists and --incremental specified)')
        return

    # Generate initial HTML
    html = generate_site_html(str(pdf_path))

    # Write initial content
    output_dir = Path(__file__).parent.parent / "static" / "sites"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{papername}.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Initial HTML written to {output_path}")

    # Run feedback loop
    run_feedback_loop(output_path, papername)

    # Take screenshot after feedback loop is complete
    site_url = f"/static/sites/{papername}.html"
    asyncio.run(take_screenshot(site_url, papername))

    # Create or update entry
    # Use the final HTML content after the loop
    with open(output_path, "r", encoding="utf-8") as f:
        final_html = f.read()
    new_entry = create_site_entry(papername, final_html, pdf_path)

    # Update sites index
    update_sites_index(sites, new_entry, index_path)

    print(f"Successfully processed {papername}")


def main():
    parser = argparse.ArgumentParser(description="Generate interactive HTML sites from academic papers.")
    parser.add_argument("papers", nargs='+', help="Paths to the PDF files to process.")
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Only process papers that are not already present in sites.json."
    )
    args = parser.parse_args()

    index_path = Path(__file__).parent.parent / "src/lib/sites.json"
    sites = load_sites_index(index_path)

    # Get modification times and sort papers (newest first)
    paper_paths_with_mtime = []
    for paper_path_str in args.papers:
        pdf_path = Path(paper_path_str)
        try:
            mtime = pdf_path.stat().st_mtime
            paper_paths_with_mtime.append((pdf_path, mtime))
        except FileNotFoundError:
            print(f"Warning: File not found, skipping: {paper_path_str}", file=sys.stderr)

    # Sort by modification time, descending (newest first)
    sorted_paper_paths = [p[0] for p in sorted(paper_paths_with_mtime, key=lambda x: x[1], reverse=True)]

    for pdf_path in tqdm(sorted_paper_paths):
        process_paper(pdf_path, args, sites, index_path)



def generate(pdf: str):
    files = [
        # Please ensure that the file is available in local system working direrctory or change the file path.
        client().files.upload(file=pdf),
    ]
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

    model_to_use = _PRIMARY_MODEL
    try:
        chunks = client().models.generate_content_stream(
            model=model_to_use,
            contents=contents,
            config=generate_content_config,
        )
        result = "".join(chunk.text for chunk in tqdm(chunks, desc=f"Generating with {model_to_use}"))
        return _parse_html(result)
    except errors.ClientError as e:
        print(f"\nResource exhausted for primary model ({model_to_use}): {e}. Falling back...")
        model_to_use = _FALLBACK_MODEL
        # Optional: Add a small delay before retrying
        # time.sleep(1)
        try:
            print(f"Attempting generation with fallback model: {model_to_use}")
            chunks = client().models.generate_content_stream(
                model=model_to_use,
                contents=contents,
                config=generate_content_config,
            )
            result = "".join(chunk.text for chunk in tqdm(chunks, desc=f"Generating with {model_to_use}"))
            return _parse_html(result)
        except Exception as fallback_e:
            print(f"\nGeneration failed with fallback model ({model_to_use}) as well: {fallback_e}")
            raise fallback_e # Re-raise the exception from the fallback attempt
    except Exception as primary_e:
        print(f"\nAn unexpected error occurred with the primary model ({model_to_use}): {primary_e}")
        raise primary_e # Re-raise other unexpected exceptions


def fix_links(html: str) -> str:
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=f"""
Please use the google search tool to fix any broken links to wikipedia in this html:

```html
{html}
```

The wikipedia links in the corrected HTML should point to the real articles in wikipedia.

Also, any text which is accidentally using **markdown** should use <strong>html tags</strong> instead.
""")
            ]
        )
    ]
    model = "gemini-2.5-flash-preview-04-17"
    tools = [
        types.Tool(google_search=types.GoogleSearch())
    ]
    generate_content_config = types.GenerateContentConfig(
        temperature=0,
        tools=tools,
        response_mime_type="text/plain",
    )
    chunks = client().models.generate_content_stream(
        model=model,
        contents=contents,
        config=generate_content_config,
    )
    return _parse_html("".join(chunk.text for chunk in chunks))



_HTML = re.compile(
    r'```html\s+(.*?)\s+```',  # Non-greedy match with whitespace handling
    re.DOTALL | re.IGNORECASE  # Allow multiline and case variations
)


def _parse_html(output: str) -> str:
    """Extract HTML content from markdown code block.

    Args:
        output: String containing markdown with HTML code block

    Returns:
        Extracted HTML content as string

    Raises:
        ValueError: If no valid HTML code block is found
    """
    match: Optional[re.Match[str]] = _HTML.search(output)
    if not match or not match.group(1):
        snippet = output[:200] + ('...' if len(output) > 200 else '')
        raise ValueError(
            f"Failed to extract HTML block. The model's response should contain:\n"
            f"1. A markdown code block wrapped in ```html\n"
            f"2. Well-formed HTML content between the markers\n"
            f"Received:\n{snippet}"
        )

    return match.group(1).strip()


# Expected response:
"""Okay, creating a full, interactive, single-file HTML visualization in the highly polished style of Bartosz Ciechanowski is a significant undertaking, typically requiring weeks or months of dedicated development per topic. His work involves deep dives into physics and engineering principles with bespoke, highly optimized WebGL or Canvas visualizations.

However, I can create a *conceptual* single-file HTML page that outlines the *story* of the paper, incorporates the key mathematical ideas, and uses JavaScript (with a library like D3.js or Plotly.js for easier plotting, embedded within the file) to create *simpler*, illustrative interactive elements. This will aim to capture the *spirit* of explaining complex concepts interactively, focusing on:

1.  **The Problem:** UHI, vulnerability, and equity.
2.  **The Strategies:** Trees, cool surfaces.
3.  **The Trade-offs:** Cost, mortality, equity, CO2, reliability.
4.  **The Model:** City-HEAT, multi-objective optimization, adaptive pathways (DPS).
5.  **The Findings:** Equity challenges with greening, robustness to climate scenarios.

This will be a simplified representation, not a full simulation, but designed to build intuition as requested.

```html
<!DOCTYPE html>
<html lang=\"en\">
<body>
</body>
</html>
```

**How to Use:**

1.  Save the code above as a single HTML file (e.g., `urban_heat_story.html`).
2.  Open the file in a modern web browser (like Chrome, Firefox, Edge, Safari).

"""

if __name__ == "__main__":
    main()
