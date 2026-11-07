#!/usr/bin/env bash
# Installs the Azure Developer CLI Foundry extensions and the Foundry Python SDKs.
# Best-effort: a failure prints a warning and never blocks the Codespace from starting.
# Installing tooling creates no Azure resources and needs no Azure login.
set -uo pipefail
cd "$(dirname "$0")/.."

if command -v azd >/dev/null 2>&1; then
  echo "    $(azd version 2>/dev/null | head -1)"
  # microsoft.foundry bundles agents, connections, inspector, projects, routines, skills, toolboxes.
  for ext in \
    microsoft.foundry \
    azure.ai.evaluations \
    azure.ai.content-understanding \
    azure.ai.dataset \
    azure.ai.finetune \
    azure.ai.models; do
    if azd ext install "$ext" --no-prompt >/dev/null 2>&1; then
      echo "    azd extension installed: $ext"
    else
      echo "    WARN: could not install azd extension $ext (retry: azd ext install $ext)"
    fi
  done
else
  echo "    WARN: azd not found; rebuild the container to install the Azure Developer CLI."
fi

if [ -x .venv/bin/pip ]; then
  .venv/bin/pip install -q -r .devcontainer/requirements-azure.txt \
    && echo "    Python SDKs installed (azure-ai-projects, azure-identity, openai)" \
    || echo "    WARN: Python SDK install failed (retry: .venv/bin/pip install -r .devcontainer/requirements-azure.txt)"
fi
