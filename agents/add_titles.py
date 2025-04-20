#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path
from site_utils import create_site_entry

def main():
    parser = argparse.ArgumentParser(description="Update site metadata in src/lib/sites.json.")
    parser.add_argument(
        "--select-site",
        action="store_true",
        help="Interactively select a single site to update.",
    )
    args = parser.parse_args()

    sites_path = Path(__file__).parent.parent / "src/lib/sites.json"

    with open(sites_path, "r", encoding="utf-8") as f:
        all_sites = json.load(f)

    sites_to_process = all_sites

    if args.select_site:
        print("Available sites:")
        for i, site in enumerate(all_sites):
            # Use title if available, otherwise paper name
            display_name = site.get("title", site.get("paper", f"Entry {i+1}"))
            print(f"{i + 1}. {display_name}")

        while True:
            try:
                selection = input(f"Select a site number to update (1-{len(all_sites)}): ")
                index = int(selection) - 1
                if 0 <= index < len(all_sites):
                    sites_to_process = [all_sites[index]]
                    break
                else:
                    print("Invalid selection. Please enter a number within the range.")
            except ValueError:
                print("Invalid input. Please enter a number.")
            except (EOFError, KeyboardInterrupt):
                print("\nSelection cancelled.")
                sys.exit(0) # Exit gracefully if user cancels

    root = Path(__file__).parent.parent
    for entry in sites_to_process:
        html_path = root / "static" / entry["path"].lstrip("/")

        try:
            with open(html_path, "r", encoding="utf-8") as f:
                html_content = f.read()
            pdf_path = next((root / 'papers').glob((entry['paper'] + '.pdf').replace('_', '*')))
            entry2 = create_site_entry(entry['paper'], html_content, pdf_path)
            del entry2['generated']
            entry.update(entry2)

        except FileNotFoundError as e:
            print(f"Warning: HTML file not found at {html_path}: {e}")
        except ValueError as e:
            print(f"Error processing {html_path}: {str(e)}")

    with open(sites_path, "w", encoding="utf-8") as f:
        json.dump(sites, f, indent=2)


if __name__ == "__main__":
    main()
