"""Tools for the Image Reader agent."""

from typing import Optional

from google.adk import Context


def analyze_image(image_url: str, question: Optional[str] = None, tool_context: Optional[Context] = None) -> dict:
    """Analyze an image and describe its contents.

    Args:
        image_url: URL or data URI of the image to analyze.
        question: Optional specific question about the image.

    Returns:
        A dict with the analysis results.
    """
    # TODO: Wire up to Gemini Vision API for image understanding
    return {
        "status": "not_implemented",
        "image_url": image_url,
        "question": question,
        "message": "Image analysis will be wired to Gemini Vision API.",
    }


def extract_text_from_image(image_url: str, tool_context: Optional[Context] = None) -> dict:
    """Extract text from an image (OCR).

    Args:
        image_url: URL or data URI of the image to extract text from.

    Returns:
        A dict with the extracted text.
    """
    # TODO: Wire up to Gemini Vision API for OCR
    return {
        "status": "not_implemented",
        "image_url": image_url,
        "message": "OCR will be wired to Gemini Vision API.",
    }