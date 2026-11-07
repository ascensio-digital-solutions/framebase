#!/usr/bin/env bash
# OPT-IN. Installs the Azure Developer CLI, the Foundry azd extensions and the Foundry Python SDKs.
# Not run automatically: it adds minutes and a few hundred MB. Run it when you start Foundry work.
# Installing tooling creates no Azure resources and needs no Azure login.
set -uo pipefail
cd "$(dirname "$0")/.."

if ! command -v azd >/dev/null 2>&1; then
  echo "==> Installing Azure Developer CLI"
  curl -fsSL https://aka.ms/install-azd.sh | bash || { echo "azd install failed"; exit 1; }
  export PATH="$HOME/.azd/bin:$PATH"
fi
echo "    $(azd version 2>/dev/null | head -1)"

# microsoft.foundry bundles agents, connections, inspector, projects, routines, skills, toolboxes.
# Add more on demand: azure.ai.evaluations, azure.ai.dataset, azure.ai.finetune, azure.ai.models,
# azure.ai.content-understanding.
azd ext install microsoft.foundry --no-prompt \
  && echo "    azd extension installed: microsoft.foundry" \
  || echo "    WARN: could not install microsoft.foundry (retry: azd ext install microsoft.foundry)"

echo "==> Foundry Python SDKs (virtualenv at .venv)"
python3 -m venv .venv \
  && .venv/bin/pip install -q -r .devcontainer/requirements-azure.txt \
  && echo "    installed: azure-ai-projects, azure-identity, openai" \
  || echo "    WARN: Python SDK install failed (is python3-venv installed?)"
