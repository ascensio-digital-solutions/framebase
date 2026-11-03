# Agents Studio — Agent Context

This file is read by Gemini CLI, AI Studio Build, and any ADK agent working on this project.

## Project identity

- **Name:** Agents Studio
- **Purpose:** Multi-agent system for image generation, image analysis, and inbox management
- **Framework:** Google ADK 2.x (`google-adk>=2.0.0`)
- **Runtime:** Python 3.10+
- **Deployment:** Cloud Run via `adk deploy cloud_run`, or AI Studio Build import

## Code conventions

- All agents live under `src/agents/<name>/agent.py`
- Tools are separate modules in each agent's `tools.py`
- Each agent has its own `__init__.py` that exports the root agent
- Use `google.adk.Context` for tool context (ADK 2.x pattern)
- Docstrings on tool functions become the OpenAPI schema for Gemini

## Environment

- `GEMINI_API_KEY` must be set in `.env` (never committed)
- `GOOGLE_GENAI_USE_VERTEXAI=TRUE` for Vertex AI; omit for AI Studio API key

## Agent structure (ADK 2.x)

```python
from google.adk import Agent
from google.adk.agents import LlmAgent

agent = LlmAgent(
    name="agent_name",
    model="gemini-2.0-flash",
    instruction="You are a...",
    tools=[tool_function],
)
```

## Key commands

```bash
adk run <agent_dir>        # CLI
adk web                    # Web UI
adk api_server             # FastAPI server
adk deploy cloud_run       # Deploy
```