#!/usr/bin/env python3
from __future__ import annotations
import PyPDF2
from bs4 import BeautifulSoup
from site_utils import create_site_entry, client
from google.genai import types  # type: ignore
from pathlib import Path
from tqdm import tqdm
from typing import Optional
import argparse
import base64
import datetime
import json
import re
import sys
import time

_PRIMARY_MODEL = "gemini-2.5-pro-exp-03-25"
_FALLBACK_MODEL = "gemini-2.5-pro-preview-03-25"
_PROMPT = f"""
I'd like you to translate the core ideas of the provided academic paper into an interactive website, drawing inspiration from the explanatory style of Bret Victor or Bartosz Ciechanowski (https://ciechanow.ski/).

The goal is a single HTML file (with Javascript and CSS inlined) that serves as a professional, well-decorated, and highly intuitive blog post exploring the paper's main concepts. A layman with a high school education in mathematics and should be able to build understanding of the paper's mathematical model and contributions mainly through interacting with javascript simulations and visualizations.

**Requirements:**

1.  **Technical:**
    * Use simulation when appropriate. Use interaction to demonstrate the mathematical concepts and build intuition for the ideas. Every visualization should always have some interactive component, always preferred over static charts.
    * Prioritize **interactive Javascript visualizations** to build intuition *before* introducing complex equations.
    * If you must make a chart, prefer using D3.js.
    * Use **MathJax** to render ALL mathematical notation. Ensure LaTeX delimiters (`$...$` for inline, `$$...$$` for display) are used correctly in the output HTML.
    * For any custom diagrams or simple simulations needed beyond standard charts, use **plain Javascript** or **p5.js** if appropriate.

2.  **Content Flow & Explanation:**
    * Start with a clear, high-level introduction to the problem the paper addresses.
    * Gradually build up the necessary concepts. **Define terms of art clearly** and provide Wikipedia links where helpful (e.g., `<a href="WIKI_URL" target="_blank">Term</a>`).
    * Focus on the **core mathematical model or central idea** of the paper. Don't try to cover everything; aim for depth on the key concept.

3.  **Handling Mathematical Models:**
    * When appropriate, write a Monte Carlo simulation which explores how the modeled system might evolve.
    * When the paper presents constrained optimization models, create interactive visualizations that allow users to adjust key input parameters (e.g., costs, resource limits, demand levels) via sliders or input fields.
    * Make visualizations genuinely interactive: use sliders for parameters, tooltips on hover for data points, potentially buttons to trigger calculation updates or simulation steps.
    * Use many small visualizations of ideas to build up intuition, rather than just relying on one or two.

5.  **Output Format & Quality:**
    * Produce a **single, self-contained HTML file**.
    * Include **comments in the Javascript code** explaining the logic, especially for visualizations and interactive elements.
    * Ensure the final output is polished, professional, and technically accurate according to the paper's content.
    * You'll probably need to generate the HTML body first before adding scripts and styles at the bottom, given your autoregressive generation of the page. 

Please generate the HTML file based on the provided paper content and these instructions.
""".strip()


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
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            sites = json.load(f)
    except FileNotFoundError:
        sites = []

    existing_papers = {entry['paper'] for entry in sites}

    for paper_path_str in tqdm(args.papers):
        pdf_path = Path(paper_path_str)

        # Sanitize filename
        papername = pdf_path.stem.replace(" ", "_")

        # Skip if incremental flag is set and paper already exists
        if args.incremental and papername in existing_papers:
            print(f'Skipping {papername} (already exists and --incremental specified)')
            continue

        html = fix_links(generate(paper_path_str))

        # Write content
        output_dir = Path(__file__).parent.parent / "static" / "sites"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{papername}.html"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        # Create or update entry
        new_entry = create_site_entry(papername, html, pdf_path)

        # Remove existing entry if found, then append the new/updated one
        sites = [entry for entry in sites if entry["paper"] != papername]
        sites.append(new_entry)

        # Sort sites alphabetically by paper name for consistency
        sites.sort(key=lambda x: x['paper'])

        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(sites, f, indent=2)

        print(f"Successfully wrote to {output_path}")



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
        print(f"Attempting generation with primary model: {model_to_use}")
        chunks = client().models.generate_content_stream(
            model=model_to_use,
            contents=contents,
            config=generate_content_config,
        )
        result = "".join(chunk.text for chunk in tqdm(chunks, desc=f"Generating with {model_to_use}"))
        return _parse_html(result)
    except google_exceptions.ResourceExhausted as e:
        print(f"Resource exhausted for primary model ({model_to_use}): {e}. Falling back...")
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
            print(f"Generation failed with fallback model ({model_to_use}) as well: {fallback_e}")
            raise fallback_e # Re-raise the exception from the fallback attempt
    except Exception as primary_e:
        print(f"An unexpected error occurred with the primary model ({model_to_use}): {primary_e}")
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
