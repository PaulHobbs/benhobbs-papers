from bs4 import BeautifulSoup
from functools import cache
from google import genai  # type: ignore
from pathlib import Path
import datetime
import os
import PyPDF2
import re


@cache
def client() -> genai.Client:
    return genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))


def extract_title(html: str) -> str:
    """Extract the page title from the first h1 element in HTML content."""
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    if not h1:
        raise ValueError("No h1 element found in HTML content")
    return h1.get_text().strip()

def extract_metadata(pdf_path: Path) -> tuple[list[str], str]:
    """Extract author and date metadata from PDF file."""
    with open(pdf_path, "rb") as f:
        pdf = PyPDF2.PdfReader(f)
        meta = pdf.metadata
        
        authors = meta.get("/Author", "")
        if authors:
            authors = [a.strip() for a in authors.split(";") if a.strip()]
        else:
            authors = ["Unknown author"]
        
        date = meta.get("/CreationDate", "")
        if date:
            # Convert PDF date format (YYYYMMDDHHmmSS) to ISO format
            try:
                clean_date = re.search(r"(\d{4})(\d{2})(\d{2})", date).groups()
                pub_date = f"{clean_date[0]}-{clean_date[1]}-{clean_date[2]}"
            except (AttributeError, ValueError):
                pub_date = ""
        else:
            pub_date = ""
        
        return authors, pub_date

def create_site_entry(papername: str, html_content: str, pdf_path: Path) -> dict:
    """Creates a dictionary entry for sites.json."""
    title = extract_title(html_content)
    # Actually, the authors should be extracted from the raw pdf using gemini flash AI!
    authors, pub_date = extract_metadata(pdf_path)
    return {
        "paper": papername,
        "path": f"/sites/{papername}.html",
        "title": title,
        "authors": authors,
        "publication_date": pub_date,
        "generated": datetime.datetime.now().isoformat()
    }