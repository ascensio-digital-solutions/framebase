# Agents Studio — Project Status

**Created:** 2026-11-03
**Platform:** Google Agent Development Kit (ADK) + Gemini Enterprise Agent Platform
**Repository:** github.com/vincent-laroche/agents-studio

## Current state

- [x] Repository created
- [x] Project scaffolded
- [ ] Image Generator agent implemented
- [ ] Image Reader agent implemented
- [ ] Inbox Manager agent implemented
- [ ] Fine-tuning pipeline set up
- [ ] Deployed to Cloud Run / Agent Engine

## Active decisions

None yet.

## Open work

1. Implement each agent with ADK 2.x (`google-adk>=2.0.0`)
2. Configure model selection (Nano Banana 2 for image gen, Gemini 3 Flash for vision/text)
3. Set up Gmail API tools for inbox manager
4. Create tuning datasets and run supervised fine-tuning in Agent Studio
5. Import into Google AI Studio Build via GitHub integration
6. Deploy agents and wire up a unified frontend

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-11-03 | Use ADK Python (code-first) as primary dev surface | Full control, local IDE, deploy anywhere |
| 2026-11-03 | GitHub repo as source of truth; AI Studio Build as iteration/ deploy target | GitHub import keeps the repo portable |