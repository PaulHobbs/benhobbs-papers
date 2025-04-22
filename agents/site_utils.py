from bs4 import BeautifulSoup
from functools import cache
from google import genai  # type: ignore
from google.genai import types  # type: ignore
from pathlib import Path
import datetime
import os
import PyPDF2
import re
import json
from pydantic import BaseModel


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


def extract_publication_date(pdf_path: Path) -> str:
    """Extract date metadata from PDF file."""
    pub_date = ""
    try:
        with open(pdf_path, "rb") as f:
            pdf = PyPDF2.PdfReader(f)
            meta = pdf.metadata
            date = meta.get("/CreationDate", "")
            if date:
                # Convert PDF date format (D:YYYYMMDDHHmmSS[+-]...) to ISO format YYYY-MM-DD
                try:
                    # Example PDF date format: D:20230418153000Z or D:20230501100000+01'00'
                    match = re.search(r"(\d{4})(\d{2})(\d{2})", date)
                    if match:
                        year, month, day = match.groups()
                        pub_date = f"{year}-{month}-{day}"
                except (
                    Exception
                ) as e:  # Catch potential errors during regex/date processing within the 'if date:' block
                    print(
                        f"Warning: Could not parse date string '{date}' from {pdf_path}: {e}"
                    )
                    # Keep pub_date as "" if parsing fails
    except Exception as e:  # Catch errors from file opening or metadata access
        print(f"Warning: Could not extract publication date from {pdf_path}: {e}")
        # Keep pub_date as ""
    return pub_date


class PDFMeta(BaseModel):
    authors: list[str]
    title: str


def _call_gemini_for_authors(first_page_text: str, pdf_path: Path) -> PDFMeta | None:
    """Calls the Gemini API to extract authors from text, requesting JSON."""
    # Use a specific, efficient model for this task and enable JSON output
    prompt = f"""
    Extract the list of authors and title from the following text, which is
    the first page of a PDF document. Return the result as a JSON object
    with a key "authors" which is a list of strings, and key "title" which
    is as string.
    
    For example:
        {{
        "authors": ["Author One", "Author Two", "Author Three"],
        "title": "Distributional outcomes of urban heat island reduction pathways under climate extremes"
        }}.

    Text:
    ---
    {first_page_text[:4000]}
    ---
    JSON Output:
    """  # Limit text length to avoid exceeding token limits
    response = client().models.generate_content(
        model="gemini-2.0-flash-001",
        contents=types.Content(role="user", parts=[types.Part.from_text(text=prompt)]),
        config={"response_mime_type": "application/json", "response_schema": PDFMeta},
    )
    return response.parsed


def extract_pdf_meta_with_gemini(pdf_path: Path) -> PDFMeta:
    """Extract authors from the first page of the PDF using AI."""
    with open(pdf_path, "rb") as f:
        pdf = PyPDF2.PdfReader(f)
        # Extract text from the first two pages, as authors are usually listed there.
        # Two pages are useful in case there's a filler page at the beginning.
        first_page_text = '\n'.join(p.extract_text() for p in pdf.pages[:2])
        if not first_page_text:
            raise ValueError(
                f"Warning: No text extracted from the first page of {pdf_path}"
            )

    # Call the helper function to interact with the Gemini API
    meta = _call_gemini_for_authors(first_page_text, pdf_path)
    if not meta:
        return PDFMeta(authors=["Unknown Author"], title="Unknown title")
    return meta


_PDF_SITE_PATH = re.compile(r"/static/([^/]*/[^/]*\.pdf)$")


def _pdf_site_path(pdf_path: Path) -> str:
    """Converts the absolute path into a relative path used for the site."""
    m = _PDF_SITE_PATH.search(str(pdf_path))
    if not m:
        raise ValueError(f"Pdf path {str(pdf_path)} does not match static/*.pdf")
    return m.group(1)


def create_site_entry(papername: str, html_content: str, pdf_path: Path) -> dict:
    """Creates a dictionary entry for sites.json."""
    pub_date = extract_publication_date(pdf_path)
    meta = extract_pdf_meta_with_gemini(pdf_path)
    return {
        "paper": papername,
        "path": f"/sites/{papername}.html",
        "title": extract_title(html_content),
        "authors": meta.authors,
        "pdf_title": meta.title,
        "pdf_site": _pdf_site_path(pdf_path),
        "publication_date": pub_date,
        "generated": datetime.datetime.now().isoformat(),
    }
