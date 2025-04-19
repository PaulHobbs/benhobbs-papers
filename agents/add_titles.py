#!/usr/bin/env python3
import json
from pathlib import Path
from src.lib.site_utils import create_site_entry


def main():
    sites_path = Path(__file__).parent.parent / "src/lib/sites.json"

    with open(sites_path, "r", encoding="utf-8") as f:
        sites = json.load(f)

    root = Path(__file__).parent.parent 
    for entry in sites:
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
