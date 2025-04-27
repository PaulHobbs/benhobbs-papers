from google import genai  # type: ignore
from google.genai import types as genai_types # For type hints
from functools import cache
import os
import time
from unittest.mock import MagicMock
from pathlib import Path
import logging
import json # For parsing fake responses

# --- Constants ---
PRIMARY_MODEL = "gemini-2.5-pro-exp-03-25"
FALLBACK_MODEL = "gemini-2.5-pro-preview-03-25"
WEAK_MODEL = "gemini-2.0-flash-001"

# --- Fake Client for Dry Run ---

logger = logging.getLogger(__name__)
# Configure basic logging if not already configured elsewhere
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class FakeGeminiResponse:
    """Mimics the structure of a Gemini response object, especially for JSON."""
    def __init__(self, text_content: str, is_json: bool = False):
        self.text = text_content
        self._is_json = is_json
        self.parsed = None
        if is_json:
            try:
                self.parsed = json.loads(text_content)
            except json.JSONDecodeError:
                logger.error(f"[DRY RUN] Fake response failed to parse as JSON: {text_content[:100]}")
                # Keep self.parsed as None

    def __str__(self):
        return self.text


class FakeGeminiClient:
    """A fake Gemini client for dry runs."""
    def __init__(self):
        logger.warning("Using FakeGeminiClient for dry run.")
        self.files = self._FakeFiles()
        self.models = self._FakeModels()

    class _FakeFiles:
        def upload(self, file: str) -> MagicMock:
            mock_file = MagicMock(spec=genai_types.File) # Use spec for better mocking
            file_path = Path(file)
            mock_file.uri = f"fake-uri:///{file_path.name}"
            # Guess mime type based on suffix, default to pdf
            if file_path.suffix.lower() == ".png":
                mock_file.mime_type = "image/png"
            elif file_path.suffix.lower() == ".html":
                 mock_file.mime_type = "text/html"
            else:
                 mock_file.mime_type = "application/pdf"
            mock_file.name = f"files/fake-{file_path.stem}-{int(time.time()*1000)}"
            logger.info(f"[DRY RUN] Faking file upload for {file}: name={mock_file.name}, mime={mock_file.mime_type}")
            return mock_file

        def delete(self, name: str) -> None:
            logger.info(f"[DRY RUN] Faking file delete for {name}")
            # Simulate potential API delay
            time.sleep(0.05)
            return None # Real API returns None on success

    class _FakeModels:
        def _get_prompt_text(self, contents) -> str:
            """Helper to extract text from various content formats."""
            prompt_text = ""
            if not contents:
                return ""
            # Handle both list[Content] and single Content object
            if isinstance(contents, list):
                content_obj = contents[0]
            elif isinstance(contents, genai_types.Content):
                 content_obj = contents
            else:
                 logger.warning(f"[DRY RUN] Unexpected contents type: {type(contents)}")
                 return ""

            if content_obj.parts:
                for part in content_obj.parts:
                    if hasattr(part, 'text') and part.text:
                        prompt_text += part.text + "\n" # Add newline for easier matching
            return prompt_text.strip()

        def generate_content_stream(self, model: str, contents: list, config: MagicMock, **kwargs) -> list:
            """Fakes the streaming response."""
            logger.info(f"[DRY RUN] Faking generate_content_stream call for model {model}")
            # Simulate API delay
            time.sleep(0.1)

            prompt_text = self._get_prompt_text(contents)
            response_text = ""

            # Determine response based on prompt content (crude simulation)
            if "Review the following HTML content" in prompt_text:
                # Simulate feedback loop ending after one iteration
                response_text = "looks good"
                logger.info("[DRY RUN] Responding with 'looks good' for feedback.")
            elif "Please use the google search tool" in prompt_text:
                 # Simulate link fixing
                 response_text = "```html\n<!DOCTYPE html><html><body><h1>Fixed Links [DRY RUN]</h1><p>Fixed <strong>HTML</strong> tags and <a href='https://en.wikipedia.org/wiki/Dry_run' target='_blank'>links</a>.</p></body></html>\n```"
                 logger.info("[DRY RUN] Responding with fake fixed HTML.")
            else: # Assume initial generation otherwise
                # Simulate initial generation
                response_text = "```html\n<!DOCTYPE html><html><body><h1>Fake Initial HTML [DRY RUN]</h1><p>Initial content with **markdown** and maybe a <a href='WIKI_URL'>bad link</a>.</p><script>console.log('dry run script');</script></body></html>\n```"
                logger.info("[DRY RUN] Responding with fake initial HTML.")

            # Simulate streaming by yielding a single chunk
            mock_chunk = MagicMock()
            mock_chunk.text = response_text
            return [mock_chunk] # Return as iterable list

        def generate_content(self, model: str, contents: list | genai_types.Content, config: dict, **kwargs) -> FakeGeminiResponse:
            """Fakes the non-streaming response, used for JSON mode."""
            logger.info(f"[DRY RUN] Faking generate_content call for model {model} with config {config}")
            # Simulate API delay
            time.sleep(0.1)

            prompt_text = self._get_prompt_text(contents)
            response_text = ""
            is_json = config.get("response_mime_type") == "application/json"

            # Determine response based on prompt content
            if "Extract the list of authors and title" in prompt_text and is_json:
                 # Simulate PDF metadata extraction
                 response_text = '{"title": "Fake PDF Title [DRY RUN]", "authors": ["Author A [DRY RUN]", "Author B [DRY RUN]"]}'
                 logger.info("[DRY RUN] Responding with fake PDF metadata JSON.")
            else:
                 # Default non-JSON response if needed, or handle other JSON cases
                 response_text = "Fake non-streaming response [DRY RUN]"
                 logger.warning(f"[DRY RUN] Unhandled generate_content case. Prompt: {prompt_text[:100]}...")

            return FakeGeminiResponse(response_text, is_json=is_json)


# --- Client Factory ---

# Remove @cache as the result now depends on the dry_run argument
# Caching could be added back with dry_run as part of the cache key if needed,
# but for simplicity, let's remove it for now.
# @cache # Removed cache
def client(dry_run: bool = False) -> genai.Client | FakeGeminiClient:
    """
    Returns a real or fake Gemini client based on the dry_run flag.

    Args:
        dry_run: If True, return the FakeGeminiClient.

    Returns:
        An instance of google.genai.Client or FakeGeminiClient.

    Raises:
        ValueError: If not in dry_run mode and GEMINI_API_KEY is not set.
    """
    if dry_run:
        # Return a new instance each time to avoid potential state issues if
        # the fake client becomes stateful later.
        return FakeGeminiClient()
    else:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set and not in dry_run mode.")
        # Consider adding caching back here for the real client if performance is critical
        return genai.Client(api_key=api_key)
