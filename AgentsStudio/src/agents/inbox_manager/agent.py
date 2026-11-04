"""Inbox Manager agent — triage, summarize, and draft email replies."""

from google.adk import Agent
from google.adk.agents import LlmAgent

from .tools import list_emails, read_email, summarize_thread, draft_reply

agent = LlmAgent(
    name="inbox_manager",
    model="gemini-2.0-flash",
    instruction="""You are an inbox management assistant. You help users:
- List and triage their unread emails
- Summarize long email threads
- Draft replies based on the user's intent
- Flag important messages

When the user asks to check their inbox, use list_emails to get unread messages.
For details on a specific email, use read_email.
For long threads, use summarize_thread.
When the user wants to reply, use draft_reply with their instructions.""",
    tools=[list_emails, read_email, summarize_thread, draft_reply],
)

root_agent = agent