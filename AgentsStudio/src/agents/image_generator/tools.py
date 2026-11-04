"""Tools for the Image Generator agent."""

from typing import Optional

from google.adk import Context


def generate_image(prompt: str, style: Optional[str] = None, tool_context: Optional[Context] = None) -> dict:
    """Generate an image from a text prompt.

    Args:
        prompt: The text description of the image to generate.
        style: Optional style guide (e.g. "photorealistic", "illustration", "watercolor").

    Returns:
        A dict with the generated image data or URL.
    """
    # TODO: Wire up to Gemini image generation or Nano Banana 2 API
    return {
        "status": "not_implemented",
        "prompt": prompt,
        "style": style,
        "message": "Image generation will be wired to Gemini / Nano Banana 2 API.",
    }