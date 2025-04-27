import asyncio
import json
from pathlib import Path
from typing import List, Optional, Dict

from prefect import flow, get_run_logger, task # Import task needed for loading index

# Import all tasks from the tasks module
from agents.workflow.tasks import (
    task_generate_initial_html,
    task_fix_links,
    task_run_feedback_loop,
    task_save_final_html,
    task_take_screenshot,
    task_extract_metadata,
    task_update_index,
)

# Helper task to load the index within the flow context if needed
@task
def load_sites_index_task(index_path: Path) -> Dict[str, Dict]:
    """Loads the sites index from sites.json into a dictionary keyed by papername."""
    logger = get_run_logger()
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            sites_list = json.load(f)
        logger.info(f"Loaded {len(sites_list)} existing entries from {index_path}")
        return {entry["paper"]: entry for entry in sites_list}
    except FileNotFoundError:
        logger.warning(f"Sites index file not found at {index_path}. Returning empty dict.")
        return {}
    except json.JSONDecodeError as e:
         logger.error(f"Error decoding JSON from {index_path}: {e}. Returning empty dict.")
         return {}


@flow(name="Create or Update Interactive Paper Sites")
def create_sites_flow(pdf_paths: List[Path], incremental: bool = False):
    """
    Orchestrates the generation of interactive websites from PDF papers.

    Args:
        pdf_paths: A list of paths to the PDF files to process.
        incremental: If True, only process papers not already present in sites.json.
    """
    logger = get_run_logger()
    logger.info(f"Starting site creation flow for {len(pdf_paths)} PDFs. Incremental: {incremental}")

    project_root = Path(__file__).parent.parent
    index_path = project_root / "src/lib/sites.json"
    existing_sites = {}
    if incremental:
        existing_sites = load_sites_index_task(index_path)
        logger.info(f"Incremental mode: Loaded {len(existing_sites)} existing site entries.")

    processed_metadata = []

    for pdf_path in pdf_paths:
        papername = pdf_path.stem.replace(" ", "_") # Basic sanitization
        logger.info(f"Processing paper: {papername} from {pdf_path}")

        if incremental and papername in existing_sites:
            logger.info(f"Skipping {papername} (already exists and --incremental specified)")
            # Add existing metadata to list if needed for a full update later?
            # Or assume incremental means only add *new* things. For now, just skip.
            continue

        try:
            # --- Main Processing Chain ---
            initial_html = task_generate_initial_html(pdf_path, papername)
            fixed_html = task_fix_links(initial_html, papername)
            final_html = task_run_feedback_loop(fixed_html, papername) # Add max_iterations if needed
            final_html_path = task_save_final_html(final_html, papername)
            # Run screenshot and metadata extraction concurrently? Prefect handles async tasks.
            # screenshot_path_future = task_take_screenshot.submit(final_html_path, papername) # Use .submit for async
            # metadata_future = task_extract_metadata.submit(final_html, pdf_path, papername)
            # For simplicity now, run sequentially
            screenshot_path = asyncio.run(task_take_screenshot(final_html_path, papername)) # task_take_screenshot is async
            metadata = task_extract_metadata(final_html, pdf_path, papername)

            # --- Collect Results ---
            # metadata = metadata_future.result()
            # screenshot_path = screenshot_path_future.result() # Wait for screenshot if needed

            # Optionally add screenshot path to metadata if needed downstream
            metadata["screenshot_path"] = str(screenshot_path)

            processed_metadata.append(metadata)
            logger.info(f"Successfully processed {papername}")

        except Exception as e:
            logger.error(f"Failed to process {papername}: {e}", exc_info=True)
            # Continue to next paper or stop flow? For now, continue.

    # --- Final Step: Update Index ---
    if processed_metadata:
        logger.info(f"Updating index with metadata for {len(processed_metadata)} processed papers.")
        task_update_index(processed_metadata)
    else:
        logger.info("No new metadata generated, skipping index update.")

    logger.info("Site creation flow finished.")


@flow(name="Update Existing Site Metadata")
def update_metadata_flow(paper_names: Optional[List[str]] = None):
    """
    Updates metadata for existing sites in sites.json without regeneration.

    Args:
        paper_names: A list of specific paper names (slugs) to update.
                     If None, updates metadata for all entries in sites.json.
    """
    logger = get_run_logger()
    logger.info(f"Starting metadata update flow. Target papers: {'All' if paper_names is None else paper_names}")

    project_root = Path(__file__).parent.parent
    index_path = project_root / "src/lib/sites.json"
    sites_dir = project_root / "static" / "sites"
    papers_dir = project_root / "papers" # Assuming PDF location

    existing_sites_dict = load_sites_index_task(index_path)
    if not existing_sites_dict:
        logger.error("Cannot update metadata: sites.json is empty or could not be loaded.")
        return

    papers_to_process = []
    if paper_names is None:
        papers_to_process = list(existing_sites_dict.keys())
        logger.info(f"Processing all {len(papers_to_process)} entries found in sites.json.")
    else:
        for name in paper_names:
            if name in existing_sites_dict:
                papers_to_process.append(name)
            else:
                logger.warning(f"Skipping '{name}': not found in sites.json.")
        logger.info(f"Processing {len(papers_to_process)} specified papers.")

    if not papers_to_process:
        logger.info("No papers selected for metadata update.")
        return

    updated_metadata = []

    for papername in papers_to_process:
        logger.info(f"Updating metadata for: {papername}")
        entry = existing_sites_dict[papername]
        html_filename = entry.get("path", f"/sites/{papername}.html").lstrip("/")
        html_path = project_root / "static" / html_filename

        # Need to reconstruct the likely PDF path based on convention or stored info
        # Assuming pdf_site stores 'category/basename.pdf' relative to papers_dir
        pdf_site_rel_path = entry.get("pdf_site")
        if not pdf_site_rel_path:
             # Try reconstructing from papername if pdf_site is missing
             logger.warning(f"Missing 'pdf_site' for {papername}. Attempting to guess PDF path.")
             # This is fragile - requires finding the PDF based only on papername
             # Example: find papers/*/{papername}.pdf or papers/{papername}.pdf
             possible_pdfs = list(papers_dir.glob(f"**/{papername}.pdf"))
             if not possible_pdfs:
                 logger.error(f"Could not find PDF for {papername} based on name convention. Skipping metadata update.")
                 continue
             elif len(possible_pdfs) > 1:
                  logger.warning(f"Found multiple possible PDFs for {papername}: {possible_pdfs}. Using the first one: {possible_pdfs[0]}")
                  pdf_path = possible_pdfs[0]
             else:
                  pdf_path = possible_pdfs[0]
                  logger.info(f"Guessed PDF path: {pdf_path}")
        else:
            pdf_path = papers_dir / pdf_site_rel_path


        if not html_path.exists():
            logger.error(f"HTML file not found for {papername} at {html_path}. Skipping metadata update.")
            continue
        if not pdf_path.exists():
             logger.error(f"PDF file not found for {papername} at {pdf_path}. Skipping metadata update.")
             continue

        try:
            # Read existing HTML
            with open(html_path, "r", encoding="utf-8") as f:
                final_html = f.read()

            # Extract metadata using the existing HTML and PDF
            metadata = task_extract_metadata(final_html, pdf_path, papername)
            updated_metadata.append(metadata)
            logger.info(f"Successfully extracted updated metadata for {papername}")

        except Exception as e:
            logger.error(f"Failed to update metadata for {papername}: {e}", exc_info=True)
            # Continue to next paper

    # --- Final Step: Update Index ---
    if updated_metadata:
        logger.info(f"Updating index with metadata for {len(updated_metadata)} processed papers.")
        task_update_index(updated_metadata)
    else:
        logger.info("No metadata successfully updated, skipping index update.")

    logger.info("Metadata update flow finished.")