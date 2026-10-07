#!/usr/bin/env bash
# postStartCommand: publication and strict verification follow startup automatically.
set -euo pipefail
umask 077
cd "$(dirname "$0")"
: "${CODESPACE_NAME:?This must run inside the user GitHub Codespace}"
command -v gh >/dev/null || { echo 'GitHub CLI is missing; rebuild the devcontainer.' >&2; exit 1; }
mkdir -p .runtime
exec 9>.runtime/launch.lock
flock -n 9 || { echo 'A launch check is already running.'; exit 1; }
accepted=0
cleanup() {
  if [[ "$accepted" != 1 ]]; then
    echo 'Launch did not pass. Withdrawing public access and stopping the DNS process.' >&2
    timeout 20 gh codespace ports visibility 8080:private -c "$CODESPACE_NAME" >/dev/null 2>&1 || echo 'Port withdrawal could not be confirmed; stopping the backend.' >&2
    if [[ -f .runtime/pid ]]; then
      PID="$(cat .runtime/pid)"
      # Never kill an unrelated process using a stale/recycled pid.
      if [[ "$PID" =~ ^[0-9]+$ ]] && [[ -r "/proc/$PID/cmdline" ]] && tr '\0' ' ' <"/proc/$PID/cmdline" | grep -q 'python edge_server.py --public-origin'; then
        kill "$PID" 2>/dev/null || true
      fi
    fi
  fi
}
trap cleanup EXIT
bash start.sh 9>&-
# Allow the GitHub forwarding service to observe the declared port.
for delay in 2 4 8 16; do
  if timeout 20 gh codespace ports visibility 8080:public -c "$CODESPACE_NAME"; then
    sleep "$delay"
    if bash verify.sh; then
      accepted=1
      exit 0
    fi
  fi
  sleep "$delay"
done
exit 1
