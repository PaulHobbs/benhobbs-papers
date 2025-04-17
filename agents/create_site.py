#!/usr/bin/env python3
from __future__ import annotations
import base64
import datetime
import json
import os
from pathlib import Path
import re
import sys
import json
import datetime
from typing import Optional
from google import genai  # type: ignore
from google.genai import types  # type: ignore

_MODEL = "gemini-2.5-pro-exp-03-25"
_PROMPT = f"""
I'd like you to translate the core ideas of the provided academic paper into an interactive website, drawing inspiration from the explanatory style of Bret Victor or Bartosz Ciechanowski (https://ciechanow.ski/).

The goal is a single HTML file (with Javascript and CSS inlined) that serves as a professional, well-decorated, and highly intuitive blog post exploring the paper's main concepts.

**Requirements:**

1.  **Libraries:**
    * Use simulation when appropriate. Stuff that moves is almost always preferred over static charts.
    * Prioritize **interactive Javascript visualizations** to build intuition *before* introducing complex equations.
    * If you must make a chart, use Chart.js or D3.js.
    * Use **MathJax** to render ALL mathematical notation. Ensure LaTeX delimiters (`$...$` for inline, `$$...$$` for display) are used correctly in the output HTML.
    * Use **Bootstrap** (via CDN link preferably, or minimal inline CSS) for overall styling, layout (containers, rows, columns), and standard components (buttons, cards).
    * For any custom diagrams or simple simulations needed beyond standard charts, use **plain Javascript** or **p5.js** if appropriate.

2.  **Content Flow & Explanation:**
    * Start with a clear, high-level introduction to the problem the paper addresses.
    * Gradually build up the necessary concepts. **Define terms of art clearly** and provide Wikipedia links where helpful (e.g., `<a href="WIKI_URL" target="_blank">Term</a>`).
    * Focus on the **core mathematical model or central idea** of the paper. Don't try to cover everything; aim for depth on the key concept.

3.  **Handling Mathematical Models:**
    * When the paper presents constrained optimization models, create interactive visualizations (using Plotly.js or D3.js if needed for custom views) that allow users to **adjust key input parameters** (e.g., costs, resource limits, demand levels) via sliders or input fields. The visualization should dynamically show how the **optimal solution** (objective function value, key decision variable values) changes in response.
    * When appropriate, write a Monte Carlo simulation which explores how the modeled system might evolve. Using a visual simulation (using p5.js or plain JS) might be appropriate over graphs.

4.  **Interactivity:**
    * Make visualizations genuinely interactive: use sliders for parameters, tooltips on hover for data points, potentially buttons to trigger calculation updates or simulation steps.

5.  **Output Format & Quality:**
    * Produce a **single, self-contained HTML file**.
    * Inline necessary Javascript and CSS. Keep inline CSS minimal; rely on Bootstrap classes.
    * Include **comments in the Javascript code** explaining the logic, especially for visualizations and interactive elements.
    * Ensure the final output is polished, professional, and technically accurate according to the paper's content.

Please generate the HTML file based on the provided paper content and these instructions.
""".strip()


def main():
    for paper in sys.argv[1:]:
      html = _parse_html(generate(paper))

      try:
          # Get input PDF path (assuming this is defined earlier)
          pdf_path = Path(paper)
          
          # Construct output path
          output_dir = Path(__file__).parent.parent / "static" / "sites"
          output_dir.mkdir(parents=True, exist_ok=True)
          
          # Sanitize filename
          papername = pdf_path.stem.replace(" ", "_")
          output_path = output_dir / f"{papername}.html"
          
          # Write content
          with open(output_path, "w", encoding="utf-8") as f:
              f.write(html)

          # Update sites index
          index_path = output_dir.parent.parent / "src" / "lib" / "sites.json"
          try:
              with open(index_path, "r", encoding="utf-8") as f:
                  sites = json.load(f)
          except (FileNotFoundError, json.JSONDecodeError):
              sites = []

          # Add new entry if not exists
          new_entry = {
              "paper": papername,
              "path": f"/static/sites/{papername}.html",
              "generated": datetime.datetime.now().isoformat()
          }
          
          if not any(entry["paper"] == papername for entry in sites):
              sites.append(new_entry)
              with open(index_path, "w", encoding="utf-8") as f:
                  json.dump(sites, f, indent=2)

          print(f"Successfully wrote to {output_path}")

      except Exception as e:
          print(f"Error generating HTML file: {str(e)}", file=sys.stderr)
          sys.exit(1)


def generate(pdf: str):
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    files = [
        # Please ensure that the file is available in local system working direrctory or change the file path.
        client.files.upload(file=pdf),
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

    chunks = client.models.generate_content_stream(
        model=_MODEL,
        contents=contents,
        config=generate_content_config,
    )
    return "".join(chunk.text for chunk in chunks)


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