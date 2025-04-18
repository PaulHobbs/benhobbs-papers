#!/usr/bin/env python3
import json
from pathlib import Path
from agents.create_site import extract_title

def main():
    sites_path = Path(__file__).parent.parent / "src/lib/sites.json"
    
    with open(sites_path, 'r', encoding='utf-8') as f:
        sites = json.load(f)

    for entry in sites:
        html_path = Path(__file__).parent.parent / "static" / entry['path'].lstrip('/')
        
        try:
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            title = extract_title(html_content)
            entry['title'] = title
            print(f"Added title '{title}' for {entry['paper']}")
            
        except FileNotFoundError:
            print(f"Warning: HTML file not found at {html_path}")
        except ValueError as e:
            print(f"Error processing {html_path}: {str(e)}")

    with open(sites_path, 'w', encoding='utf-8') as f:
        json.dump(sites, f, indent=2)

if __name__ == "__main__":
    main()
