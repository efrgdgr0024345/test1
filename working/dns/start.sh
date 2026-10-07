#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
: "${CODESPACE_NAME:?This runtime is intended for a GitHub Codespace}"
: "${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:?Missing Codespaces forwarding domain}"
LIFETIME_SECONDS="${LIFETIME_SECONDS:-10800}"
case "$LIFETIME_SECONDS" in
  3600|7200|10800) ;;
  *) echo "Set LIFETIME_SECONDS to 3600, 7200, or 10800"; exit 2 ;;
esac
mkdir -p .runtime
if [[ -f .runtime/pid ]] && kill -0 "$(cat .runtime/pid)" 2>/dev/null; then
  echo "DNS service is already running."
  exit 0
fi
ORIGIN="https://${CODESPACE_NAME}-8080.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
nohup .venv/bin/python edge_server.py --public-origin "$ORIGIN" --port 8080 --lifetime "$LIFETIME_SECONDS" >.runtime/server.log 2>&1 &
echo $! > .runtime/pid
for _ in {1..50}; do
  if curl -fsS --max-time 1 http://127.0.0.1:8080/healthz >/dev/null; then
    echo "Private loopback service started."
    echo "Now run: bash working/dns/make-public.sh"
    exit 0
  fi
  sleep .2
done
cat .runtime/server.log >&2 || true
exit 1
