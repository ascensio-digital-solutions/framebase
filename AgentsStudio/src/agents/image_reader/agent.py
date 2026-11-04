"""Image Reader agent — analyze and describe images using Gemini Vision."""

from google.adk import Agent
from google.adk.agents import LlmAgent

from .tools import analyze_image, extract_text_from_image

agent = LlmAgent(
    name="image_reader",
    model="gemini-2.0-flash",
    instruction="""You are an image analysis assistant. You can:
- Describe what's in an image in detail
- Extract text from images (OCR)
- Answer questions about image content
- Compare multiple images

Use the analyze_image tool for general image understanding and extract_text_from_image
when the user specifically wants text extracted.""",
    tools=[analyze_image, extract_text_from_image],
)

root_agent = agent