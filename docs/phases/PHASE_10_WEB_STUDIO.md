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
- [x] Container image built and verified (2026-11-08) via `az acr build` in the existing `crhairsoldevcus` registry (digest `sha256:5dbe0a8e…`, commit `7db04882`).
- [x] Staging deployment (2026-11-08): Container App `framebase-web-staging` in the existing `cae-hair-sol-dev-cus` environment (`rg-hair-sol-dev-cus`, Central US), 0.25 vCPU / 0.5 GiB, scale 0 to 2, system-assigned identity pulling from ACR. URL: `https://framebase-web-staging.blacksea-985163be.centralus.azurecontainerapps.io`. Smoke-tested: `/healthz` reports the deployed commit, the app shell and client routes load, `/v1/library/*` returns `cloud_not_configured`. **No secrets, no Cloudflare connection, no media.** Redeploy with `Web/scripts/deploy-staging.sh`.
- [x] Authentication in front of staging (2026-11-08): Microsoft Entra sign-in via Container Apps Easy Auth. App registration `Framebase Web Studio (staging)` (client `b293bb66-c800-4bdd-a576-b6e221a309be`, single tenant `216ba82d-04e0-43d2-8c07-91efcf6a36cd`), user assignment required with only Vincent assigned. Verified: unauthenticated `curl` gets 401, browser navigation gets a 302 to the Microsoft login with no AADSTS error, `/healthz` is the only open path. The client secret lives only in the Container App secret store (`microsoft-provider-authentication-secret`) and **expires 2027-11-08**: rotate with `az ad app credential reset` and `az containerapp secret set`, then restart the revision. `LIBRARY_ACCESS_PROTECTED=true` is set. Sign-in with a real browser session has not been exercised yet.
- [ ] Add the Cloudflare connection to staging (`FRAMEBASE_CLOUD_API_URL`, `FRAMEBASE_CLOUD_PAIRING_SECRET` as a Container App secret, ideally via Key Vault). Needs the target Worker's pairing secret.
- [ ] Move to a dedicated `rg-hsc-framebase-eus2` environment and Bicep definitions once the Milestone 0 inventory is done (the app is stateless, so this is a redeploy).

### Milestone 2 status (library workspace, read-only)

- [x] Server-side Cloudflare client: ephemeral-key device enrollment (`library.read` only), session refresh by repeating the signed challenge, paged catalog bootstrap, derivative proxy.
- [x] In-memory catalog index with folder roll-up counts, album/tag/search filters, cursor paging, trash excluded. Tested against a fake Worker that verifies real ECDSA signatures.
- [x] Explorer tree, Grid/List views with real thumbnails, preview panel (checked visually against synthetic data only).
- [x] Live connection to the **dev** Worker (2026-11-08, `npm run live:check`, run by Vincent): enrollment with a real signature worked and registered device `framebase-web-studio` (`library.read`). The dev catalog is synthetic test data (19,977 assets in "Phase 2/3/4 fixture" folders), loaded in 58 s because every bootstrap page re-reads all tables. Thumbnails returned HTTP 503 (the dev Worker has no image-transformation service configured). The web server now warms the catalog at boot and has a 60 s request timeout.
- [ ] Live connection to the **prod** Worker, where the real HSC media is expected. Needs: the prod pairing secret (`~/.env` only has `FRAMEBASE_API_DEV_ENROLLMENT_SECRET`), explicit approval to enroll a device on production, and a check that the prod catalog actually holds the assets and that its Worker has image transformations.
- [ ] Faster catalog loading: incremental sync from `/v1/changes` or a lighter listing endpoint, instead of re-reading every table per page.
- [ ] Authentication in front of the web server before any deployment (Cloudflare Access or Entra). Library routes are disabled in production until `LIBRARY_ACCESS_PROTECTED=true`.
- [ ] Writes (move, tag, trash, upload) and incremental sync via `/v1/changes`. Reads only for now.

Observed 2026-11-07 (read-only): `framebase-api-dev` and `framebase-api-prod` Workers are deployed and healthy, `hsc-media-delivery` serves `assets.hairsolutions.co`, and `framebase-personal-api-prod` is not deployed. Whether `framebase-catalog-prod` actually holds the 8,252 HSC assets was not verified, because the available narrow token cannot read D1.

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
