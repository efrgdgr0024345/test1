#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/python -m pip install --disable-pip-version-check --no-cache-dir -r requirements.txt
mkdir -p .runtime
chmod 700 .runtime
echo "Black Cat DNS dependencies installed."
