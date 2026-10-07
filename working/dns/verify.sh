#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
SESSION=.runtime/session.json
[[ -s "$SESSION" ]] || { echo "Session file not found; run start.sh first"; exit 1; }
ORIGIN="$(.venv/bin/python - <<'PY'
import json
print(json.load(open(".runtime/session.json"))["public_origin"])
PY
)"
DASH="$(.venv/bin/python - <<'PY'
import json
print(json.load(open(".runtime/session.json"))["dashboard"])
PY
)"
DOH="$(.venv/bin/python - <<'PY'
import json
print(json.load(open(".runtime/session.json"))["doh"])
PY
)"
echo "1/4 HTTPS endpoint..."
curl --proto '=https' --tlsv1.2 -fsS --max-time 10 "$DASH" >/dev/null

echo "2/4 Plain HTTP must not serve application content..."
set +e
HEADERS="$(mktemp)"
curl -sS --max-time 8 -D "$HEADERS" -o /dev/null "${ORIGIN/https:/http:}"
RC=$?
set -e
if [[ $RC -eq 0 ]]; then
  CODE="$(awk 'toupper($1) ~ /^HTTP\// {code=$2} END{print code}' "$HEADERS")"
  LOCATION="$(awk 'BEGIN{IGNORECASE=1} /^Location:/ {sub(/\r$/,"",$2); print $2}' "$HEADERS" | tail -1)"
  if [[ ! "$CODE" =~ ^30[1278]$ || "$LOCATION" != https://* ]]; then
    echo "FAIL: public HTTP served or did not force HTTPS (status=$CODE location=$LOCATION)" >&2
    rm -f "$HEADERS"; exit 1
  fi
fi
rm -f "$HEADERS"

echo "3/4 DNS-over-HTTPS protocol..."
DOH="$DOH" .venv/bin/python smoke.py

echo "4/4 Record verified state..."
.venv/bin/python - <<'PY'
import json
p=".runtime/session.json"
d=json.load(open(p)); d["deployment_verified"]=True
open(p,"w").write(json.dumps(d,indent=2))
print("\nVERIFIED HTTPS-ONLY PUBLIC SESSION")
print("Dashboard:",d["dashboard"])
print("DoH:",d["doh"])
PY
