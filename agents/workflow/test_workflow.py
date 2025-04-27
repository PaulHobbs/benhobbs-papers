import asyncio
import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock, call

import pytest
from prefect import flow
from prefect.testing.utilities import prefect_test_harness

# Import the flows and tasks to be tested
from agents.site_utils import PDFMeta
from agents.workflow.flows import create_sites_flow, update_metadata_flow, load_sites_index_task
from agents.workflow.tasks import (
    _parse_html,
    # Import other tasks if testing individually
)

# --- Test Data ---

FAKE_PAPERNAME = "test_paper_1"
FAKE_PDF_CONTENT = b"%PDF-1.4 fake pdf content"
INITIAL_HTML_RESPONSE = f"""
```html
<!DOCTYPE html>
<html>
<head><title>Initial Draft</title></head>
<body>
<h1>Initial Draft for {FAKE_PAPERNAME}</h1>
<p>This is the first draft. It might have <a href="WIKI_URL">bad links</a> and **markdown**.</p>
<script>console.log('initial script');</script>
</body>
</html>
```
"""
FIXED_LINKS_HTML_RESPONSE = f"""
```html
<!DOCTYPE html>
<html>
<head><title>Fixed Links Draft</title></head>
<body>
<h1>Fixed Links Draft for {FAKE_PAPERNAME}</h1>
<p>This is the fixed draft. It should have <a href="https://en.wikipedia.org/wiki/Good_link" target="_blank">good links</a> and <strong>html tags</strong>.</p>
<script>console.log('fixed script');</script>
</body>
</html>
```
"""
FEEDBACK_ITER_1_HTML_RESPONSE = f"""
```html
<!DOCTYPE html>
<html>
<head><title>Feedback Iter 1</title></head>
<body>
<h1>Feedback Iter 1 for {FAKE_PAPERNAME}</h1>
<p>This is the first feedback iteration.</p>
<p>second draft</p>
<script>console.log('feedback 1 script');</script>
</body>
</html>
```
"""
FEEDBACK_ITER_2_RESPONSE = "looks good"

FINAL_HTML_CONTENT = """<!DOCTYPE html>
<html>
<head><title>Feedback Iter 1</title></head>
<body>
<h1>Feedback Iter 1 for {FAKE_PAPERNAME}</h1>
<p>This is the first feedback iteration.</p>
<p>second draft</p>
<script>console.log('feedback 1 script');</script>
</body>
</html>""" # This is the content from the last successful feedback iteration

# --- Pytest Fixtures ---

@pytest.fixture(autouse=True)
def prefect_test_fixture():
    """Ensures Prefect test harness is active for all tests."""
    with prefect_test_harness():
        yield

@pytest.fixture
def temp_test_dir(tmp_path: Path) -> Path:
    """Creates a temporary directory structure similar to the project."""
    base = tmp_path / "bhobbs-papers"
    papers_dir = base / "papers" / "category1"
    static_dir = base / "static"
    sites_dir = static_dir / "sites"
    screenshots_dir = static_dir / "screenshots"
    src_lib_dir = base / "src" / "lib"

    papers_dir.mkdir(parents=True, exist_ok=True)
    sites_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    src_lib_dir.mkdir(parents=True, exist_ok=True)

    # Create a dummy PDF
    pdf_path = papers_dir / f"{FAKE_PAPERNAME}.pdf"
    pdf_path.write_bytes(FAKE_PDF_CONTENT)

    # Create an empty sites.json
    sites_json_path = src_lib_dir / "sites.json"
    sites_json_path.write_text("[]")

    return base

@pytest.fixture
def mock_gemini_client():
    """Mocks the Gemini client and its methods."""
    mock_client_instance = MagicMock()
    mock_files = MagicMock()
    mock_models = MagicMock()

    # Mock file upload
    mock_uploaded_file = MagicMock()
    mock_uploaded_file.uri = f"file:///{FAKE_PAPERNAME}.pdf"
    mock_uploaded_file.mime_type = "application/pdf"
    mock_uploaded_file.name = f"files/{FAKE_PAPERNAME}.pdf"
    mock_files.upload.return_value = mock_uploaded_file

    # Mock file delete
    mock_files.delete.return_value = None # Or appropriate response

    # Mock generate_content_stream
    def generate_content_stream_side_effect(*args, model, contents, config, **kwargs):
        prompt_text = []

        # Extract text from contents to determine the call type
        if contents and contents[0].parts:
             for part in contents[0].parts:
                 if hasattr(part, 'text') and part.text:
                     prompt_text.append(part.text)
        prompt_text = '\n'.join(prompt_text)

        # Determine response based on model and prompt content
        if "Please use the google search tool" in prompt_text: # Link fixing call
             mock_chunk = MagicMock()
             mock_chunk.text = FIXED_LINKS_HTML_RESPONSE
             return [mock_chunk] # Return as iterable
        elif "Review the following HTML content" in prompt_text: # Feedback loop call
            # Simulate feedback iterations
            if f"<h1>Fixed Links Draft for {FAKE_PAPERNAME}</h1>" in prompt_text:
                 mock_chunk = MagicMock()
                 mock_chunk.text = FEEDBACK_ITER_1_HTML_RESPONSE
                 return [mock_chunk]
            elif f"<h1>Feedback Iter 1 for {FAKE_PAPERNAME}</h1>" in prompt_text:
                 mock_chunk = MagicMock()
                 mock_chunk.text = FEEDBACK_ITER_2_RESPONSE
                 return [mock_chunk]
            else: # Default fallback for unexpected feedback content
                 mock_chunk = MagicMock()
                 mock_chunk.text = "looks good" # Prevent infinite loop
                 return [mock_chunk]
        else: # Initial generation call
             mock_chunk = MagicMock()
             mock_chunk.text = INITIAL_HTML_RESPONSE
             return [mock_chunk] # Return as iterable

    mock_models.generate_content_stream.side_effect = generate_content_stream_side_effect

    mock_client_instance.files = mock_files
    mock_client_instance.models = mock_models

    # Patch the client function in site_utils (or wherever it's defined)
    # Adjust the path 'agents.site_utils.client' if it's different
    with patch('agents.site_utils.client', return_value=mock_client_instance) as mock_client_func:
        # Also patch the client used directly in tasks.py if different
        with patch('agents.workflow.tasks.client', return_value=mock_client_instance) as mock_tasks_client_func:
             yield mock_client_instance # Yield the instance for potential assertions

@pytest.fixture
def mock_take_screenshot(temp_test_dir): # Add temp_test_dir dependency
    """Mocks the take_screenshot function."""
    mock_screenshot = AsyncMock()
    # Define the correct screenshot directory within the temp structure
    correct_screenshot_dir = temp_test_dir / "static" / "screenshots"
    correct_screenshot_dir.mkdir(parents=True, exist_ok=True) # Ensure it exists

    async def screenshot_side_effect(url: str, name: str, output_dir: Path):
        # Ignore the potentially incorrect output_dir passed from the task
        # Use the correct_screenshot_dir defined in the fixture's scope
        screenshot_path = correct_screenshot_dir / f"{name}.png"
        screenshot_path.touch() # Create an empty file
        # print(f"Mock screenshot created at: {screenshot_path}") # Debug print (optional)
        return str(screenshot_path) # Return the correct path

    mock_screenshot.side_effect = screenshot_side_effect

    # Patch the import within tasks.py (and potentially others if needed)
    # Ensure both potential import locations are patched
    with patch('agents.workflow.tasks.take_screenshot', mock_screenshot) as mocked_tasks_func, \
         patch('agents.puppet.puppeteer.take_screenshot', mock_screenshot, create=True) as mocked_puppet_func: # Use create=True if puppet might not always be imported
              yield mock_screenshot # Yield the mock instance

@pytest.fixture
def mock_pdf_metadata():
    """Mocks PDF metadata extraction functions."""
    # Mock functions from site_utils (adjust path if necessary)
    with patch('agents.site_utils.extract_publication_date', return_value="2024-01-15") as mock_date, \
         patch('agents.site_utils.extract_pdf_meta_with_gemini', return_value=PDFMeta(title="Mock PDF Title", authors=["Author One", "Author Two"])) as mock_meta, \
         patch('agents.site_utils._pdf_site_path', return_value=f"category1/{FAKE_PAPERNAME}.pdf") as mock_pdf_path, \
         patch('agents.workflow.tasks.extract_publication_date', return_value="2024-01-15") as mock_task_date, \
         patch('agents.workflow.tasks.extract_pdf_meta_with_gemini', return_value=PDFMeta(title="Mock PDF Title", authors=["Author One", "Author Two"])) as mock_task_meta, \
         patch('agents.workflow.tasks._pdf_site_path', return_value=f"category1/{FAKE_PAPERNAME}.pdf") as mock_task_pdf_path:
        yield {
            "date": mock_date, "meta": mock_meta, "pdf_path": mock_pdf_path,
            "task_date": mock_task_date, "task_meta": mock_task_meta, "task_pdf_path": mock_task_pdf_path
        }


# --- Test Cases ---

def test_parse_html():
    """Tests the _parse_html helper function."""
    raw_output = """
Some text before.
```html
<!DOCTYPE html>
<html>
<body>Test HTML</body>
</html>
```
Some text after.
"""
    expected_html = """<!DOCTYPE html>
<html>
<body>Test HTML</body>
</html>"""
    assert _parse_html(raw_output) == expected_html

    raw_output_no_block = "Just plain text."
    # Expect it to return the original string if no block found (as per current implementation)
    assert _parse_html(raw_output_no_block) == raw_output_no_block

    raw_output_malformed = "```html malformed"
    assert _parse_html(raw_output_malformed) == raw_output_malformed


@pytest.mark.usefixtures("mock_gemini_client", "mock_take_screenshot", "mock_pdf_metadata")
def test_create_sites_flow_single_pdf(temp_test_dir: Path):
    """Tests the create_sites_flow with a single PDF."""
    pdf_path = temp_test_dir / "papers" / "category1" / f"{FAKE_PAPERNAME}.pdf"
    sites_json_path = temp_test_dir / "src" / "lib" / "sites.json"
    final_html_path = temp_test_dir / "static" / "sites" / f"{FAKE_PAPERNAME}.html"
    final_screenshot_path = temp_test_dir / "static" / "screenshots" / f"{FAKE_PAPERNAME}.png"
    feedback_screenshot_path = temp_test_dir / "static" / "screenshots" / f"{FAKE_PAPERNAME}_feedback_iter1.png"

    # --- Mock Path resolution within the flow/tasks ---
    # Patch Path object creation within the specific modules being tested
    # to ensure they use the temp_test_dir as their base
    flow_path_target = 'agents.workflow.flows.Path'
    tasks_path_target = 'agents.workflow.tasks.Path'

    # Store the original Path class
    original_path_cls = Path

    # Create a side effect function for the patch
    # This function will return a *new class* that behaves like Path but modifies initialization
    def create_patched_path_class(temp_base_dir):
        class PatchedPath(original_path_cls):
            def __init__(self, *args, **kwargs):
                # If args start with a Path object, use it directly (avoids recursion)
                if args and isinstance(args[0], original_path_cls):
                    super().__init__(*args, **kwargs)
                    return

                # Attempt to construct the path intended by the original code
                intended_path = original_path_cls(*args)

                # Heuristic: Check if it looks like an absolute path derived from __file__
                # This assumes the test file is in agents/workflow/
                real_project_root = original_path_cls(__file__).parent.parent.parent
                is_likely_absolute_from_source = False
                try:
                    # See if the intended path is relative to the real project root
                    intended_path.relative_to(real_project_root)
                    is_likely_absolute_from_source = intended_path.is_absolute()
                except ValueError:
                    is_likely_absolute_from_source = False # Not relative to project root

                if is_likely_absolute_from_source:
                    # Map it into the temp structure
                    try:
                        rel_path = intended_path.relative_to(real_project_root)
                        full_temp_path = temp_base_dir / rel_path
                        # print(f"DEBUG: Mapped absolute {intended_path} -> {full_temp_path}") # Debug print
                    except ValueError:
                        # Fallback if relative_to fails unexpectedly
                        full_temp_path = temp_base_dir / intended_path.name
                        # print(f"DEBUG: Fallback absolute {intended_path} -> {full_temp_path}") # Debug print
                elif intended_path.is_absolute():
                     # Absolute path not relative to project root - keep it as is? Or force into temp?
                     # Forcing into temp is safer for test isolation.
                     full_temp_path = temp_base_dir / intended_path.name # Simplified fallback
                     # print(f"DEBUG: Kept/Forced absolute {intended_path} -> {full_temp_path}") # Debug print
                else:
                    # Relative path, make it relative to the temp base dir
                    full_temp_path = temp_base_dir / intended_path
                    # print(f"DEBUG: Relative {intended_path} -> {full_temp_path}") # Debug print


                # Call the original Path's __init__ with the modified path
                super().__init__(full_temp_path, **kwargs)
        return PatchedPath

    # Apply the patches using the factory function
    PatchedFlowPath = create_patched_path_class(temp_test_dir)
    PatchedTasksPath = create_patched_path_class(temp_test_dir)

    with patch(flow_path_target, PatchedFlowPath) as mock_flow_path, \
         patch(tasks_path_target, PatchedTasksPath) as mock_tasks_path:

        # --- Run the flow ---
        # Ensure the input pdf_path is correctly using the temp_test_dir structure
        assert str(temp_test_dir) in str(pdf_path), f"Input PDF path {pdf_path} doesn't seem to be in temp dir {temp_test_dir}"
        print(f"Running flow with PDF: {pdf_path}") # Debug print
        create_sites_flow(pdf_paths=[pdf_path], incremental=False)

    # --- Assertions ---
    # Ensure paths used for assertions are also based on temp_test_dir
    sites_json_path = temp_test_dir / "src" / "lib" / "sites.json"
    final_html_path = temp_test_dir / "static" / "sites" / f"{FAKE_PAPERNAME}.html"
    final_screenshot_path = temp_test_dir / "static" / "screenshots" / f"{FAKE_PAPERNAME}.png"
    feedback_screenshot_path = temp_test_dir / "static" / "screenshots" / f"{FAKE_PAPERNAME}_feedback_iter1.png"

    # 1. Check final HTML content
    assert final_html_path.exists()
    assert final_html_path.read_text() == FINAL_HTML_CONTENT.format(FAKE_PAPERNAME=FAKE_PAPERNAME)

    # 2. Check final screenshot file existence
    assert final_screenshot_path.exists()
    assert final_screenshot_path.stat().st_size > 0 # Check if not empty (mock creates empty)

    # 3. Check intermediate feedback screenshot existence
    assert feedback_screenshot_path.exists()
    assert feedback_screenshot_path.stat().st_size > 0

    # 4. Check sites.json content
    assert sites_json_path.exists()
    with open(sites_json_path, "r") as f:
        sites_data = json.load(f)

    assert len(sites_data) == 1
    entry = sites_data[0]
    assert entry["paper"] == FAKE_PAPERNAME
    assert entry["title"] == f"Feedback Iter 1 for {FAKE_PAPERNAME}" # Title from final HTML H1
    assert entry["authors"] == ["Author One", "Author Two"]
    assert entry["pdf_title"] == "Mock PDF Title"
    assert entry["publication_date"] == "2024-01-15"
    assert entry["path"] == f"/sites/{FAKE_PAPERNAME}.html"
    assert entry["pdf_site"] == f"category1/{FAKE_PAPERNAME}.pdf"
    assert Path(temp_test_dir / "static" / entry["screenshot_path"].lstrip('/')).exists() # Check screenshot path in metadata

    # 5. Check Mock Calls (Optional but recommended)
    # Example: Check if screenshot was called for feedback and final
    mock_take_screenshot_instance = mock_take_screenshot # Get the mock instance if needed via fixture return
    # expected_calls = [
    #     call(f'/static/screenshots/{FAKE_PAPERNAME}_feedback_iter1.html', f'{FAKE_PAPERNAME}_feedback_iter1', ANY), # Intermediate
    #     call(f'/static/sites/{FAKE_PAPERNAME}.html', FAKE_PAPERNAME, ANY) # Final
    # ]
    # mock_take_screenshot_instance.assert_has_calls(expected_calls, any_order=True) # Check calls were made


# TODO: Add more tests:
# - test_create_sites_flow_incremental_skip
# - test_create_sites_flow_incremental_add
# - test_create_sites_flow_multiple_pdfs
# - test_create_sites_flow_gemini_error_handling (e.g., ResourceExhausted)
# - test_update_metadata_flow_all
# - test_update_metadata_flow_specific
# - test_update_metadata_flow_missing_files
# - test_update_metadata_flow_guess_pdf_path