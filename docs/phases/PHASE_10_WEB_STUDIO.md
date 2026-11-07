# Phase 10 — Framebase Web Studio

**Goal:** A private, browser-based creative workspace on top of the existing Framebase catalog: an Explorer, a **Create** chat (generation), an **Understand** chat (vision and organization), and a central Grid / List / Board workspace with a separate preview/output panel. It complements the native Mac app; it does not replace it.

**Status:** Foundation scaffolded (2026-11-07). Dev container, `Web/` workspace, CI and a manual image-publish workflow exist. No Azure resource, Cloudflare change, deployment or live provider call has been made. Everything beyond Milestone 1 is planned and gated below.

Source of the product and architecture decisions: `Framebase 2.0 — Azure AI Vision & Hair Concierge Brain Migration Plan.md` and the web-studio build specification agreed in chat on 2026-11-06. This file is the focused implementation plan that `docs/MASTER_ROADMAP.md` requires before production code begins.

## Boundaries

1. **D1 stays authoritative** for assets, folders, albums, tags and Trash. PostgreSQL holds only chats, board layouts, generation jobs and preferences, referencing existing asset IDs.
2. **The browser never talks to Cloudflare directly.** `Web/server` calls the Framebase API server-side with a scoped device token. No raw R2/D1 credentials, no permissive CORS, no tokens in browser code.
3. **Library spaces stay isolated** (Phase 9). A command resolves inside exactly one library; there is no merged cross-library grid, search or agent capability.
4. **One command surface** serves manual UI actions and both agents (`Web/packages/contracts`). Persistent commands carry an operation ID and an expected revision; stale writes are rejected.
5. **Originals are immutable.** Generated or edited images are new assets with provenance; removing a board placement never deletes the underlying asset.
6. **Nothing is deployed by this plan.** Azure resource creation, Container Apps deployment, DNS/Access, secrets and production changes each need explicit approval. A roadmap or phase plan is never deployment approval.
7. **Spend stays inside the $500/month planning envelope** with per-service limits and generation concurrency controls.

## Repository layout

```text
.devcontainer/         Lean Codespaces dev container (Node 22, gh, Azure CLI); Azure/Foundry tooling is opt-in
.mcp.json              Project MCP servers for Claude Code: Azure MCP, Foundry MCP (remote), Microsoft Learn
.vscode/mcp.json       The same MCP servers for VS Code / Copilot
Web/
  app/                 React + Vite workspace shell
  server/              Hono API, serves the built app in the container image
  packages/contracts/  Zod commands, receipts and workspace events
  Dockerfile           Single image: API + built app
.github/workflows/
  web-ci.yml           typecheck, lint, format, tests, build, container smoke test (Linux)
  web-image.yml        manual: build and push an immutable image to ACR via GitHub OIDC
```

The macOS `ci.yml` ignores `Web/**` and `.devcontainer/**` because macOS minutes bill at roughly 10x.

## Milestones and gates

| #   | Milestone          | Deliverable                                                                  | Completion gate                                                    |
| --- | ------------------ | ---------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| 0   | Verify foundations | Catalog/API inventory, brain location, Azure resources, model routes, budget | Proven ownership and connectivity; no duplicate catalog or corpus  |
| 1   | GitHub foundation  | Dev container, web skeleton, container, CI, infrastructure definitions       | Reproducible cloud build and a tested staging deployment           |
| 2   | Library workspace  | Explorer, grid/list, preview, uploads, organization via the Cloudflare API   | Real catalog operations work; native compatibility preserved       |
| 3   | Connected agents   | Both chats, model selectors, shared tools, knowledge retrieval               | Either chat operates both central panels reliably                  |
| 4   | Board and vision   | React Flow canvas, OCR, classification, organization review                  | Layout survives reload; asset identity stays consistent            |
| 5   | Creative studio    | Generation, reference selection, iterative edits, automatic saving           | Brief-to-library workflow with provenance and recovery             |
| 6   | GPU specialization | Optional custom-model container on Azure Container Apps GPU                  | Quality gain, routing compatibility and measured cost demonstrated |
| 7   | Release hardening  | Recovery, access isolation, performance, operations                          | Full acceptance suite passes against staging                       |

### Milestone 1 status

- [x] Lean dev container, port forwarding and recommended-secret names.
- [x] `Web/` workspace: contracts, API (`/healthz`, `/v1/config`, `/v1/commands` validation), app shell with resizable/collapsible panels.
- [x] Local verification: typecheck, ESLint, Prettier, 20 unit tests, production bundle served by the API.
- [x] `web-ci.yml` (Linux) and manual `web-image.yml` (OIDC to ACR, no deploy).
- [ ] Container image built and smoke-tested (runs in `web-ci.yml`; Docker was not available on the authoring Mac).
- [ ] Bicep infrastructure under `infra/azure/` (needs the Milestone 0 resource inventory first).
- [ ] Azure OIDC federated credential and the `staging` environment with required reviewers.
- [ ] Staging deployment and smoke test (approval-gated).

### Milestone 0 questions that block later work

- Where does the authoritative Hair Concierge corpus and live index reside (Google Vertex RAG today)? Do not build a second migration until this is answered.
- Which Azure region and services are available for the Container Apps, PostgreSQL and optional GPU workloads (East US 2 per the Azure plan; verify per service).
- OpenRouter: which models support vision plus tools, which image endpoints support references/editing, and what the real per-generation cost is.
- Repository visibility: the repo was observed as non-private on 2026-11-07. Confirm this is intended before any prompts, evaluation data or customer material is committed.

## Acceptance test (end state)

Open an email inspiration board, ask **Understand** to find relevant references, ask **Create** to produce a brand-informed image, refine it in chat, and have the finished asset appear in the correct collection without downloading, re-uploading or losing context.

## Reliability rules for generation (Milestone 5)

- Jobs persist independently of the browser tab.
- Retries resume failed steps. An interrupted catalog registration must not trigger a second paid generation.
- An uncertain provider outcome moves the job to `needs_reconciliation` instead of resubmitting.
- Each result records prompt, reference asset versions, model/provider, settings, knowledge sources and parent result.
