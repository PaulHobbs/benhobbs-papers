from google import genai  # type: ignore
from functools import cache
import os


@cache
def client() -> genai.Client:
    return genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))


PRIMARY_MODEL = "gemini-2.5-pro-exp-03-25"
FALLBACK_MODEL = "gemini-2.5-pro-preview-03-25"
WEAK_MODEL = "gemini-2.0-flash-001"