#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mkdir -p data
export HOME="${HOME:-/Users/leoyuan}"
export USER="${USER:-leoyuan}"
export LOGNAME="${LOGNAME:-leoyuan}"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${HOME}/.nvm/versions/node/v24.15.0/bin:${PATH:-}"

PY="${LEOJARVIS_PY:-${ROOT}/.venv/bin/python}"
if [[ ! -x "$PY" ]]; then
  echo "LeoJarvis launchd startup failed: missing Python at $PY" >&2
  exit 78
fi

exec "$PY" -m leojarvis.main
