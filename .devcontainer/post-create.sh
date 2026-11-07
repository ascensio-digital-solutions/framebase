#!/usr/bin/env bash
# Runs once after the Codespace/dev container is created. Idempotent and safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Web workspace"
if [ -f Web/package-lock.json ]; then npm ci --prefix Web; else npm install --prefix Web; fi

echo "==> Cloud API (wrangler, vitest)"
if [ -f Cloud/apps/api/package-lock.json ]; then npm ci --prefix Cloud/apps/api; fi

echo "==> Local env file (git-ignored)"
[ -f Web/.env.local ] || cp Web/.env.example Web/.env.local

echo "==> Python venv"
[ -d .venv ] || python -m venv .venv
if [ "${FRAMEBASE_INSTALL_PYTHON:-0}" = "1" ]; then
  .venv/bin/pip install -r MediaWorkshop/requirements.txt -r AgentsStudio/requirements.txt
else
  echo "    Skipped heavy Python deps. Re-run with FRAMEBASE_INSTALL_PYTHON=1 to install them."
fi

cat <<'MSG'

Framebase Web Studio is ready.
  cd Web && npm run dev        # web app :5173 + API :8788
  cd Web && npm run check      # typecheck + lint + test
  az login --use-device-code   # when you need Azure
  gh auth status               # GitHub CLI is pre-installed
MSG
