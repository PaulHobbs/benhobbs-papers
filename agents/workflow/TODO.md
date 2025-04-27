# Workflow Implementation TODO

This document outlines the steps required to implement the paper site generation and metadata update workflow using Prefect, as designed in `DESIGN.md`.

## Implementation Steps

1.  **Install Prefect:**
    *   Add Prefect to the project's dependencies. This might involve updating `requirements.txt` or `pyproject.toml` and running `pip install -r requirements.txt` or `poetry install`.

2.  **Create Workflow Directory:**
    *   Create the directory `agents/workflow/`.

3.  **Define Prefect Tasks (`agents/workflow/tasks.py`):**
    *   Create the file `agents/workflow/tasks.py`.
    *   Import necessary libraries (Prefect, google-generativeai, PyPDF2, BeautifulSoup, pydantic, pathlib, asyncio, etc.).
    *   Define each task using the `@task` decorator:
        *   `task_generate_initial_html`: Implement the logic to call Gemini for initial HTML generation.
        *   `task_fix_links`: Implement the logic to call Gemini for link fixing and markdown conversion.
        *   `task_run_feedback_loop`: Implement the iterative feedback loop. **Inside the loop, save intermediate HTML and call the screenshot function.**
        *   `task_save_final_html`: Implement saving the final HTML string to a file.
        *   `task_extract_metadata`: Implement metadata extraction logic (HTML title, PDF metadata via PyPDF2 and Gemini).
        *   `task_update_index`: Implement loading `sites.json`, merging/sorting entries, and writing back.

4.  **Define Prefect Flows (`agents/workflow/flows.py`):**
    *   Create the file `agents/workflow/flows.py`.
    *   Import necessary tasks from `agents.workflow.tasks`.
    *   Define the `create_sites_flow` using the `@flow` decorator. Implement the logic to iterate through papers, call the relevant tasks in sequence, and collect metadata for the final index update. Handle the `incremental` flag logic.
    *   Define the `update_metadata_flow` using the `@flow` decorator. Implement the logic to load `sites.json`, identify papers, read existing HTML/PDF paths, call `task_extract_metadata`, and collect metadata for the final index update.

5.  **Refactor `agents/site_utils.py`:**
    *   Remove the `create_site_entry` function as its logic will be integrated into tasks.
    *   Ensure remaining utility functions (`client`, `extract_title`, `extract_publication_date`, `extract_pdf_meta_with_gemini`, `_pdf_site_path`) are clean and usable by the new tasks.

6.  **Create Command-Line Entry Point (`run_pipeline.py`):**
    *   Create the file `run_pipeline.py`.
    *   Use `argparse` to handle command-line arguments (e.g., PDF paths, `--incremental`, paper names for update).
    *   Based on the arguments, import and call either `create_sites_flow.serve()` or `update_metadata_flow.serve()` (or just `.run()` for simple execution).

7.  **Remove Old Scripts:**
    *   Delete `agents/create_site.py`.
    *   Delete `agents/add_titles.py`.

8.  **Add Dependencies and Imports:**
    *   Ensure all necessary libraries are imported in the relevant files (`tasks.py`, `flows.py`, `run_pipeline.py`, `site_utils.py`).
    *   Verify project dependencies are correctly listed.

9.  **Implement Error Handling and Logging:**
    *   Add `try...except` blocks where necessary within tasks to handle potential API errors, file errors, etc.
    *   Use Prefect's logging capabilities (`prefect.get_run_logger()`) for better visibility into pipeline execution.

10. **Testing:**
    *   Write unit tests for individual tasks where appropriate.
    *   Run the flows with sample data to verify correct execution, caching, and output.
    *   Test both `create_sites_flow` (with and without `--incremental`) and `update_metadata_flow`.

This TODO list provides a clear path for implementing the designed workflow.