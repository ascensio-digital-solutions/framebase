# Dev container

Lean on purpose: one prebuilt Node 22 image, GitHub CLI, Azure CLI, SSH access, and four VS Code extensions. `post-create.sh` only installs the `Web/` dependencies.

## Opt-in extras

| Need                                                  | Run                                                                                                                 |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `azd` + Foundry extensions + Foundry Python SDKs      | `bash .devcontainer/install-azure-tooling.sh`                                                                       |
| Cloudflare Worker development (`wrangler`, API tests) | `npm ci --prefix Cloud/apps/api`                                                                                    |
| Python pipelines (MediaWorkshop, AgentsStudio)        | `python3 -m venv .venv && .venv/bin/pip install -r MediaWorkshop/requirements.txt -r AgentsStudio/requirements.txt` |
| Docker image builds                                   | Use the `Web CI` workflow; local Docker-in-Docker is not installed                                                  |
| PostgreSQL                                            | Not needed yet. Add a sidecar when the library workspace milestone needs it                                         |

## MCP servers

`/.mcp.json` (Claude Code) and `/.vscode/mcp.json` (VS Code) point at Azure MCP, the remote Foundry MCP and Microsoft Learn. They cost nothing until a tool uses them and need `az login` for Azure data.
