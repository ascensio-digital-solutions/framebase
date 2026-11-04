# Agents Studio

Multi-agent system built with Google Agent Development Kit (ADK) and deployed via Google Agent Studio / Gemini Enterprise Agent Platform.

## Agents

| Agent | Model | Purpose |
|---|---|---|
| **Image Generator** | Nano Banana 2 / Gemini | Generate images from text prompts |
| **Image Reader** | Gemini 3 Flash | Read, analyze, and describe images |
| **Inbox Manager** | Gemini 3 Flash | Triage, summarize, and draft email replies |

## Architecture

```
agents-studio/
├── src/
│   └── agents/
│       ├── image_generator/    # Text → image generation agent
│       ├── image_reader/       # Image → text analysis agent
│       └── inbox_manager/      # Email triage & response agent
├── Makefile                    # run, test, lint, deploy targets
├── requirements.txt            # Python dependencies
└── GEMINI.md                   # Agent context for Gemini CLI / AI Studio
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and add your `GEMINI_API_KEY`.

## Usage

```bash
# Interactive CLI
make run AGENT=image_generator

# Web UI (all agents)
make web

# API server
make api
```

## Deploy

Agents deploy to Cloud Run via ADK:

```bash
make deploy AGENT=image_generator
```

Or import this repo directly into [Google AI Studio Build](https://aistudio.google.com) via **Import from GitHub**.

## Fine-tuning

Agent Studio supports Gemini Supervised Tuning and Preference Tuning. Tuning configs live alongside each agent in `tuning/`.