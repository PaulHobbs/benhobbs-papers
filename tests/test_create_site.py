import pytest
import PyPDF2
from pathlib import Path
from agents.create_site import extract_title, extract_metadata

SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<body>
  <h1>Test Title</h1>
  <p>Content</p>
</body>
</html>
"""

MULTIPLE_H1_HTML = """
<html>
  <h1>First Title</h1>
  <h1>Second Title</h1>
</html>
"""

NO_H1_HTML = "<div>No title here</div>"

WHITESPACE_H1 = "<h1>   Extra Spaces   </h1>"

NESTED_HTML = """
<div>
  <section>
    <h1>Nested Title</h1>
  </section>
</div>
"""

@pytest.mark.parametrize("html,expected", [
    (SAMPLE_HTML, "Test Title"),
    (MULTIPLE_H1_HTML, "First Title"),
    (WHITESPACE_H1, "Extra Spaces"),
    (NESTED_HTML, "Nested Title"),
])
def test_extract_title_valid(html: str, expected: str):
    assert extract_title(html) == expected

def test_extract_title_missing_h1():
    with pytest.raises(ValueError) as exc_info:
        extract_title(NO_H1_HTML)
    assert "No h1 element found" in str(exc_info.value)


@pytest.fixture
def sample_pdf(tmp_path):
    pdf_path = tmp_path / "test.pdf"
    with open(pdf_path, "wb") as f:
        writer = PyPDF2.PdfWriter()
        writer.add_blank_page(612, 792)
        writer.add_metadata({
            "/Author": "John Doe; Jane Smith",
            "/CreationDate": "D:20240102130405"
        })
        writer.write(f)
    return pdf_path

def test_extract_metadata_valid(sample_pdf):
    authors, date = extract_metadata(sample_pdf)
    assert authors == ["John Doe", "Jane Smith"]
    assert date == "2024-01-02"

def test_extract_metadata_missing_fields(tmp_path):
    pdf_path = tmp_path / "empty.pdf"
    with open(pdf_path, "wb") as f:
        writer = PyPDF2.PdfWriter()
        writer.add_blank_page(612, 792)
        writer.write(f)
    
    authors, date = extract_metadata(pdf_path)
    assert authors == ["Unknown author"]
    assert date == ""