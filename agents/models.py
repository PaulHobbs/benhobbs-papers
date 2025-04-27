# agents/models.py
import google.api_core.exceptions as google_errors
from google.cloud.aiplatform_v1beta1.types import GenerateContentConfig, Content
from google.cloud.aiplatform_v1beta1 import types
from google.cloud.aiplatform import Client # Assuming this is the client type
import logging

logger = logging.getLogger(__name__)

# Add other model-related constants or functions here if needed

def _call_gemini_stream(
    gemini_client: Client,
    model_name: str,
    contents: list[Content],
    generate_content_config: GenerateContentConfig,
) -> str:
    """Helper to call generate_content_stream and join chunks."""
    logger.info(f"Calling model: {model_name}")
    chunks = gemini_client.models.generate_content_stream(
        model=model_name,
        contents=contents,
        config=generate_content_config,
    )
    result = "".join(chunk.text for chunk in chunks)
    logger.info(f"Successfully received content from {model_name}")
    return result


def generate_content_with_attachment(
    gemini_client: Client,
    contents: list[Content],
    generate_content_config: GenerateContentConfig,
    primary_model: str,
    fallback_model: str,
    uploaded_file_name: str # Need the file name to delete
) -> str:
    """
    Calls the Gemini model with provided content and configuration,
    handling primary/fallback models and file cleanup.

    Args:
        gemini_client: The initialized Gemini client.
        contents: The content to send to the model (including file parts).
        generate_content_config: The generation configuration.
        primary_model: The name of the primary model to use.
        fallback_model: The name of the fallback model to use on ResourceExhausted error.
        uploaded_file_name: The resource name of the uploaded file to delete afterwards.

    Returns:
        The generated text result.

    Raises:
        Exception: If generation fails with both primary and fallback models,
                   or if an unexpected error occurs.
    """
    result = ""
    try:
        result = _call_gemini_stream(
            gemini_client=gemini_client,
            model_name=primary_model,
            contents=contents,
            generate_content_config=generate_content_config,
        )

    except google_errors.ResourceExhausted as e:
        logger.warning(f"Resource exhausted for primary model ({primary_model}): {e}. Falling back...")
        try:
            result = _call_gemini_stream(
                gemini_client=gemini_client,
                model_name=fallback_model,
                contents=contents,
                generate_content_config=generate_content_config,
            )
        except Exception as fallback_e:
            logger.error(f"Generation failed with fallback model ({fallback_model}) as well: {fallback_e}")
            raise # Re-raise fallback error

    except Exception as primary_e:
        logger.error(f"An unexpected error occurred with the primary model ({primary_model}): {primary_e}")
        raise primary_e # Re-raise other primary errors

    finally:
        # Clean up uploaded file in finally block to ensure it runs after success or failure
        try:
            gemini_client.files.delete(name=uploaded_file_name)
            logger.info(f"Deleted uploaded file: {uploaded_file_name}")
        except Exception as delete_e:
            logger.error(f"Failed to delete uploaded file: {delete_e}")

    return result