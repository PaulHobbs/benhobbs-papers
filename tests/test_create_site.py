import pytest
import PyPDF2
import json
import argparse
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open, call
from agents import create_site # Import the module itself

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


# --- Tests for main function ---

@patch('agents.create_site.argparse.ArgumentParser')
@patch('agents.create_site.Path')
@patch('builtins.open', new_callable=mock_open)
@patch('agents.create_site.generate')
@patch('agents.create_site.fix_links')
@patch('agents.create_site.create_site_entry')
@patch('agents.create_site.tqdm', lambda x: x) # Mock tqdm to just return the iterable
def test_main_incremental_flag(
    mock_create_site_entry: MagicMock,
    mock_fix_links: MagicMock,
    mock_generate: MagicMock,
    mock_open_func: MagicMock,
    mock_path: MagicMock,
    mock_argparse: MagicMock
):
    """Tests the --incremental flag functionality."""

    # --- Setup Mocks ---
    # Mock Path object behavior
    mock_index_path = MagicMock()
    mock_output_dir = MagicMock()
    mock_pdf_path_existing = MagicMock(spec=Path)
    mock_pdf_path_existing.stem = "existing_paper"
    mock_pdf_path_new = MagicMock(spec=Path)
    mock_pdf_path_new.stem = "new_paper"

    # Configure Path() calls
    # Path(__file__).parent.parent / "src/lib/sites.json"
    mock_path.return_value.parent.parent.__truediv__.return_value = mock_index_path
    # Path(__file__).parent.parent / "static" / "sites"
    mock_path.return_value.parent.parent.__truediv__.return_value.__truediv__.return_value = mock_output_dir
    # Path(paper_path_str) calls
    mock_path.side_effect = [
        mock_path.return_value, # For __file__
        mock_pdf_path_existing, # First paper arg
        mock_pdf_path_new       # Second paper arg
    ]


    # Mock generate, fix_links, create_site_entry
    mock_generate.return_value = "raw_html"
    mock_fix_links.return_value = "fixed_html"
    mock_create_site_entry.side_effect = [
        {"paper": "new_paper", "title": "New Title", "other": "data1"}, # Called only for new paper in incremental
        {"paper": "existing_paper", "title": "Existing Title Updated", "other": "data2"}, # Called first when not incremental
        {"paper": "new_paper", "title": "New Title Updated", "other": "data3"},      # Called second when not incremental
    ]

    # Mock initial sites.json content
    initial_sites_content = json.dumps([{"paper": "existing_paper", "title": "Existing Title", "other": "old_data"}])
    mock_open_func.side_effect = [
        mock_open(read_data=initial_sites_content).return_value, # Read existing sites.json
        mock_open().return_value, # Write HTML for new paper
        mock_open().return_value, # Write updated sites.json
        # Reset for non-incremental run
        mock_open(read_data=initial_sites_content).return_value, # Read existing sites.json again
        mock_open().return_value, # Write HTML for existing paper
        mock_open().return_value, # Write HTML for new paper
        mock_open().return_value, # Write updated sites.json
    ]

    # --- Test with --incremental ---
    print("\nTesting with --incremental...")
    # Mock argparse results for incremental run
    args_incremental = argparse.Namespace(
        papers=["path/to/existing_paper.pdf", "path/to/new_paper.pdf"],
        incremental=True
    )
    mock_argparse.return_value.parse_args.return_value = args_incremental

    create_site.main()

    # Assertions for incremental run
    mock_generate.assert_called_once_with("path/to/new_paper.pdf")
    mock_fix_links.assert_called_once_with("raw_html")
    mock_create_site_entry.assert_called_once_with("new_paper", "fixed_html", mock_pdf_path_new)
    mock_output_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)
    # Check HTML write for the new paper
    mock_open_func.assert_any_call(mock_output_dir / "new_paper.html", "w", encoding="utf-8")
    # Check final sites.json write
    handle = mock_open_func() # Get the mock file handle for the last write
    written_data_incremental = json.loads(handle.write.call_args[0][0])
    expected_data_incremental = [
        {"paper": "existing_paper", "title": "Existing Title", "other": "old_data"},
        {"paper": "new_paper", "title": "New Title", "other": "data1"}
    ]
    assert sorted(written_data_incremental, key=lambda x: x['paper']) == sorted(expected_data_incremental, key=lambda x: x['paper'])


    # --- Reset mocks for non-incremental run ---
    print("\nTesting without --incremental...")
    mock_generate.reset_mock()
    mock_fix_links.reset_mock()
    mock_create_site_entry.reset_mock()
    mock_output_dir.mkdir.reset_mock()
    # Reset Path side effect for the second run
    mock_path.side_effect = [
        mock_path.return_value, # For __file__
        mock_pdf_path_existing, # First paper arg
        mock_pdf_path_new       # Second paper arg
    ]
    # Reset create_site_entry side effect for the second run (needs 2 return values now)
    mock_create_site_entry.side_effect = [
        {"paper": "existing_paper", "title": "Existing Title Updated", "other": "data2"},
        {"paper": "new_paper", "title": "New Title Updated", "other": "data3"},
    ]


    # --- Test without --incremental ---
    # Mock argparse results for non-incremental run
    args_non_incremental = argparse.Namespace(
        papers=["path/to/existing_paper.pdf", "path/to/new_paper.pdf"],
        incremental=False
    )
    mock_argparse.return_value.parse_args.return_value = args_non_incremental

    create_site.main()

    # Assertions for non-incremental run
    assert mock_generate.call_count == 2
    mock_generate.assert_has_calls([
        call("path/to/existing_paper.pdf"),
        call("path/to/new_paper.pdf")
    ], any_order=True) # Order might vary based on tqdm iteration

    assert mock_fix_links.call_count == 2
    mock_fix_links.assert_called_with("raw_html") # Called twice with the same mock return from generate

    assert mock_create_site_entry.call_count == 2
    mock_create_site_entry.assert_has_calls([
         call("existing_paper", "fixed_html", mock_pdf_path_existing),
         call("new_paper", "fixed_html", mock_pdf_path_new)
    ], any_order=True)

    assert mock_output_dir.mkdir.call_count == 2 # Called once per paper processed

    # Check HTML writes
    mock_open_func.assert_any_call(mock_output_dir / "existing_paper.html", "w", encoding="utf-8")
    mock_open_func.assert_any_call(mock_output_dir / "new_paper.html", "w", encoding="utf-8")

    # Check final sites.json write
    handle = mock_open_func() # Get the mock file handle for the last write
    written_data_non_incremental = json.loads(handle.write.call_args[0][0])
    expected_data_non_incremental = [
        {"paper": "existing_paper", "title": "Existing Title Updated", "other": "data2"},
        {"paper": "new_paper", "title": "New Title Updated", "other": "data3"}
    ]
    assert sorted(written_data_non_incremental, key=lambda x: x['paper']) == sorted(expected_data_non_incremental, key=lambda x: x['paper'])
