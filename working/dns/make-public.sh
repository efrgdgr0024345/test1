#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
: "${CODESPACE_NAME:?Run this inside the Codespace}"
command -v gh >/dev/null
# GitHub's public forwarded port remains in the default forwarding protocol.
# The public address itself is HTTPS. Do NOT switch the port protocol to HTTPS:
# GitHub documents that doing so automatically makes a public port private.
gh codespace ports visibility 8080:public -c "$CODESPACE_NAME"
sleep 2
bash verify.sh
