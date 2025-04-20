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
                except Exception as e: # Catch potential errors during regex/date processing within the 'if date:' block
                    print(f"Warning: Could not parse date string '{date}' from {pdf_path}: {e}")
                    # Keep pub_date as "" if parsing fails
    except Exception as e: # Catch errors from file opening or metadata access
        print(f"Warning: Could not extract publication date from {pdf_path}: {e}")
        # Keep pub_date as ""
    return pub_date


def _call_gemini_for_authors(first_page_text: str, pdf_path: Path) -> list[str] | None:
    """Calls the Gemini API to extract authors from text, requesting JSON."""
    try:
        # Use a specific, efficient model for this task and enable JSON output
        prompt = f"""
        Extract the list of authors from the following text, which is the first page of a PDF document.
        Return the result as a JSON object with a single key "authors" which is a list of strings.
        For example: {{"authors": ["Author One", "Author Two", "Author Three"]}}.
        If no authors can be identified, return {{"authors": ["Unknown author"]}}.

        Text:
        ---
        {first_page_text[:4000]}
        ---
        JSON Output:
        """ # Limit text length to avoid exceeding token limits

        class Author(BaseModel):
            authors: list[str]

        response = client().models.generate_content(
            model='gemini-2.0-flash-001',
            contents=types.Content(role="user", parts=[
                types.Part.from_text(text=prompt)
            ]),
            config={
                'response_mime_type':'application/json',
                'response_schema': Author
            }
        )
        return response.parsed.authors

    except Exception as e:
        print(f"Warning: Error during Gemini API call for {pdf_path}: {e}")
        return None


def extract_authors_with_ai(pdf_path: Path) -> list[str]:
    """Extract authors from the first page of the PDF using AI."""
    try:
        with open(pdf_path, "rb") as f:
            pdf = PyPDF2.PdfReader(f)
            # Extract text from the first page, as authors are usually listed there.
            first_page_text = pdf.pages[0].extract_text()
            if not first_page_text:
                print(f"Warning: No text extracted from the first page of {pdf_path}")
                return ["Unknown author"]

        # Call the helper function to interact with the Gemini API
        return _call_gemini_for_authors(first_page_text, pdf_path) or ["Unknown"]

    except Exception as e:
        print(f"Warning: Could not extract authors using AI from {pdf_path}: {e}")
        return ["Unknown author"]


def create_site_entry(papername: str, html_content: str, pdf_path: Path) -> dict:
    """Creates a dictionary entry for sites.json."""
    title = extract_title(html_content)
    authors = extract_authors_with_ai(pdf_path)
    pub_date = extract_publication_date(pdf_path)
    return {
        "paper": papername,
        "path": f"/sites/{papername}.html",
        "title": title,
        "authors": authors,
        "publication_date": pub_date,
        "generated": datetime.datetime.now().isoformat()
    }
