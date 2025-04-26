import requests
import os
from urllib.parse import urljoin
from bs4 import BeautifulSoup

def download_pdfs_from_url(url, base_url, output_dir="downloaded_pdfs"):
    """
    Downloads PDF files linked from a given URL.

    Args:
        url (str): The URL of the webpage to scrape.
        base_url (str): The base URL to use for resolving relative links.
        output_dir (str): The directory to save the downloaded PDFs.
    """
    print(f"Fetching content from {url}...")
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return

    soup = BeautifulSoup(response.content, 'html.parser')
    pdf_links = []

    for link in soup.find_all('a', href=True):
        href = link['href']
        if href.lower().endswith('.pdf'):
            absolute_url = urljoin(base_url, href)
            pdf_links.append(absolute_url)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")

    print(f"Found {len(pdf_links)} PDF links.")

    for pdf_url in pdf_links:
        file_name = os.path.basename(pdf_url)
        file_path = os.path.join(output_dir, file_name)

        if os.path.exists(file_path):
            print(f"Skipping {file_name}: already exists.")
            continue

        print(f"Downloading {file_name}...")
        try:
            pdf_response = requests.get(pdf_url, stream=True, timeout=10)
            pdf_response.raise_for_status()

            with open(file_path, 'wb') as f:
                for chunk in pdf_response.iter_content(chunk_size=8192):
                    f.write(chunk)

            print(f"Downloaded {file_name}")

        except requests.exceptions.RequestException as e:
            print(f"Error downloading {file_name} from {pdf_url}: {e}")
        except IOError as e:
            print(f"Error writing file {file_name}: {e}")


if __name__ == "__main__":
    target_url = "https://hobbsgroup.johnshopkins.edu/publications.html"
    base_url = "https://hobbsgroup.johnshopkins.edu/"
    download_pdfs_from_url(target_url, base_url)