#!/usr/bin/env bash
# Compatibility entry point. Launch now includes publication, verification and rollback.
set -euo pipefail
cd "$(dirname "$0")"
exec bash launch.sh
