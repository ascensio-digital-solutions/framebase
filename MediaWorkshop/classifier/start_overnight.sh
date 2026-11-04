#!/usr/bin/env bash
# Overnight runner with sleep prevention via caffeinate
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$SCRIPT_DIR/.venv/bin/python"
RUNNER="$SCRIPT_DIR/run_overnight.py"
LOG="$SCRIPT_DIR/overnight_run.log"

echo "================================================================================"
echo "LAUNCHING FRAMEBASE MEDIA OS OVERNIGHT CLASSIFIER"
echo "Preventing macOS sleep with caffeinate (-dimsu)..."
echo "Logging output to: $LOG"
echo "================================================================================"

/usr/bin/caffeinate -dimsu "$PYTHON" "$RUNNER" 2>&1 | tee -a "$LOG"

