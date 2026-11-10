#!/usr/bin/env bash
# Runs once after the Codespace/dev container is created. Idempotent and safe to re-run.
# Deliberately small: only what `npm run dev` needs. Everything else is opt-in.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Web workspace"
if [ -f Web/package-lock.json ]; then npm ci --prefix Web; else npm install --prefix Web; fi

echo "==> Local env file (git-ignored)"
[ -f Web/.env.local ] || cp Web/.env.example Web/.env.local

cat <<'MSG'

Framebase Web Studio is ready.
  cd Web && npm run dev        # web app :5173 + API :8788
  cd Web && npm run check      # typecheck + lint + test

Opt-in extras (not installed by default, see .devcontainer/README.md):
  bash .devcontainer/install-azure-tooling.sh   # azd + Foundry extensions + Python SDKs
MSG
