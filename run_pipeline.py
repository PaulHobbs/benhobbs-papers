#!/usr/bin/env python3
import argparse
from pathlib import Path
import sys

# Add agents directory to sys.path to allow imports like agents.workflow.flows
# This assumes run_pipeline.py is in the project root
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from agents.workflow.flows import create_sites_flow, update_metadata_flow

def main():
    parser = argparse.ArgumentParser(
        description="Run Prefect workflows for generating or updating paper sites.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate sites for specific PDFs, overwriting existing ones
  python run_pipeline.py create papers/paper1.pdf papers/paper2.pdf

  # Generate sites for all PDFs in the papers directory, only adding new ones
  python run_pipeline.py create --incremental papers/*.pdf

  # Update metadata for all existing sites in sites.json
  python run_pipeline.py update

  # Update metadata for specific existing sites
  python run_pipeline.py update --papers paper1_slug paper2_slug
"""
    )

    subparsers = parser.add_subparsers(dest="command", required=True, help="Sub-command help")

    # --- Create command ---
    parser_create = subparsers.add_parser("create", help="Generate new sites from PDFs")
    parser_create.add_argument(
        "pdf_files",
        metavar="PDF_FILE",
        nargs='+',
        help="Paths to the PDF files to process (supports glob patterns like papers/*.pdf)."
    )
    parser_create.add_argument(
        "--incremental",
        action="store_true",
        help="Only process papers that are not already present in sites.json."
    )

    # --- Update command ---
    parser_update = subparsers.add_parser("update", help="Update metadata for existing sites")
    parser_update.add_argument(
        "--papers",
        metavar="PAPER_NAME",
        nargs='*', # 0 or more arguments
        help="Specific paper names (slugs) to update. If omitted, updates all."
    )

    args = parser.parse_args()

    if args.command == "create":
        # Expand glob patterns
        pdf_paths = []
        for pattern in args.pdf_files:
            # Use rglob for potentially nested directories if needed, or just glob
            expanded_paths = list(project_root.glob(pattern))
            if not expanded_paths:
                 print(f"Warning: Glob pattern '{pattern}' did not match any files.", file=sys.stderr)
            pdf_paths.extend(expanded_paths)

        # Filter out non-files just in case
        pdf_paths = [p for p in pdf_paths if p.is_file()]

        if not pdf_paths:
            print("Error: No valid PDF files found to process.", file=sys.stderr)
            sys.exit(1)

        print(f"Running 'create_sites_flow' for {len(pdf_paths)} PDF(s)...")
        create_sites_flow(pdf_paths=pdf_paths, incremental=args.incremental)
        print("Create flow finished.")

    elif args.command == "update":
        # If --papers is provided but empty list, it means update all (same as not providing it)
        paper_names_to_update = args.papers if args.papers else None
        target = "all sites" if paper_names_to_update is None else f"{len(paper_names_to_update)} specific site(s)"
        print(f"Running 'update_metadata_flow' for {target}...")
        update_metadata_flow(paper_names=paper_names_to_update)
        print("Update flow finished.")

if __name__ == "__main__":
    main()