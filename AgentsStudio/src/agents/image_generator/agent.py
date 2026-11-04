"""Image Generator agent — text-to-image generation using Gemini / Nano Banana."""

from google.adk import Agent
from google.adk.agents import LlmAgent

from .tools import generate_image

agent = LlmAgent(
    name="image_generator",
    model="gemini-2.0-flash",
    instruction="""You are an image generation assistant. When the user describes an image they want,
call the generate_image tool with their description. Be creative and helpful.
If the user's prompt is vague, ask clarifying questions before generating.""",
    tools=[generate_image],
)

root_agent = agent