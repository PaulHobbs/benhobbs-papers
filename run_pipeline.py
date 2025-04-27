#!/usr/bin/env python3
from absl import app
from absl import flags
from pathlib import Path
import sys

# Add agents directory to sys.path to allow imports like agents.workflow.flows
# This assumes run_pipeline.py is in the project root
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from agents.workflow.flows import create_sites_flow, update_metadata_flow

FLAGS = flags.FLAGS

flags.DEFINE_enum('command', None, ['create', 'update'],
                  'The command to execute: "create" or "update".',
                  required=True)
flags.DEFINE_multi_string('pdf_files', [],
                          'Paths to the PDF files to process for the "create" command (supports glob patterns).')
flags.DEFINE_boolean('incremental', False,
                     'For the "create" command, only process papers not already in sites.json.')
flags.DEFINE_multi_string('papers', [],
                          'Specific paper names (slugs) to update for the "update" command. If omitted, updates all.')
# Note: The --dry-run flag is defined in agents/workflow/model.py and will be available here too.

def main(argv):
    # argv[0] is the program name, argv[1:] are the positional arguments.
    # absl handles flag parsing before calling main.

    if FLAGS.command == "create":
        if not FLAGS.pdf_files:
             print("Error: --pdf_files must be provided for the 'create' command.", file=sys.stderr)
             sys.exit(1)

        # Expand glob patterns
        pdf_paths = []
        for pattern in FLAGS.pdf_files:
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
        create_sites_flow(pdf_paths=pdf_paths, incremental=FLAGS.incremental)
        print("Create flow finished.")

    elif FLAGS.command == "update":
        # If --papers is provided but empty list, it means update all (same as not providing it)
        paper_names_to_update = FLAGS.papers if FLAGS.papers else None
        target = "all sites" if paper_names_to_update is None else f"{len(paper_names_to_update)} specific site(s)"
        print(f"Running 'update_metadata_flow' for {target}...")
        update_metadata_flow(paper_names=paper_names_to_update)
        print("Update flow finished.")


if __name__ == "__main__":
    app.run(main)
