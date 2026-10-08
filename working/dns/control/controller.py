#!/usr/bin/env python3
"""On-demand GitHub Codespaces controller. Run only in GitHub Actions.

Requires BLACKCAT_CODESPACES_PAT as a repository Actions secret. Never puts
the token in source code, command.json, logs, step summaries, or artifacts.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = "efrgdgr0024345/test1"
DISPLAY_NAME = "Black Cat DNS"
PREFIX = "https://api.github.com"
TOKEN = os.environ.get("BLACKCAT_CODESPACES_PAT", "")
SAFE_STATES = ("Available", "Starting", "Provisioning", "Queued")

def api(method, path, data=None):
    url = PREFIX + path
    payload = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(url, data=payload, method=method, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + TOKEN,
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": "BlackCat-Codespaces-Controller/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            body = response.read(500000)
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        # Do not display response bodies; they might include sensitive details.
        raise RuntimeError("GitHub Codespaces API returned HTTP " + str(exc.code)) from None

def owned():
    items = []
    # Only inspect Codespaces belonging to this repository and this user.
    for page in range(1, 4):
        result = api("GET", "/user/codespaces?per_page=100&page=" + str(page))
        batch = result.get("codespaces", [])
        for item in batch:
            if item.get("repository", {}).get("full_name", "").lower() == REPO.lower():
                items.append(item)
        if len(batch) < 100:
            break
    return items

def select(items):
    tagged = [x for x in items if x.get("display_name") == DISPLAY_NAME]
    if tagged:
        return sorted(tagged, key=lambda x: x.get("created_at", ""), reverse=True)[0]
    if len(items) == 1:
        # Adopt the single existing Codespace that the user already opened.
        return items[0]
    if len(items) > 1:
        raise RuntimeError("Several Codespaces exist for this repository; refusing to alter an ambiguous one.")
    return None

def report(item, operation):
    if not item:
        print("Black Cat DNS: no Codespace currently exists in the repository.")
        return
    name = item["name"]
    state = item.get("state", "unknown")
    base = "https://" + name + "-8080.app.github.dev"
    print("Black Cat DNS operation:", operation)
    print("Codespace:", name)
    print("GitHub state:", state)
    print("HTTPS hostname:", base)
    print("DNS-capability path: stored only inside the Codespace at working/dns/.runtime/session.json")
    print("The hostname is NOT proof that the DNS endpoint is working.")
    print("Only the Codespace's own deployment verification can confirm live DoH.")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as out:
            out.write("## Black Cat DNS Codespace\n")
            out.write("Operation: `" + operation + "`  \n")
            out.write("Codespace: `" + name + "`  \n")
            out.write("State: `" + state + "`  \n")
            out.write("Public HTTPS host (not yet a DoH proof): " + base + "  \n")
            out.write("The full DoH address is in `working/dns/.runtime/session.json` within the Codespace.  \n")

def main():
    if os.environ.get("GITHUB_REPOSITORY", "").lower() != REPO.lower():
        raise RuntimeError("Repository mismatch; refusing to control Codespaces")
    command = json.loads(Path("working/dns/control/request.json").read_text())
    operation = command.get("operation")
    if operation not in ("status", "start", "stop", "restart"):
        raise RuntimeError("Invalid operation; use status, start, stop, or restart")
    if not TOKEN:
        raise RuntimeError("Missing BLACKCAT_CODESPACES_PAT Actions secret. Configure once in GitHub repository Settings > Secrets and variables > Actions. Never paste the token into ChatGPT.")
    current = select(owned())
    if operation == "status":
        return report(current, operation)
    if operation == "start":
        if current and current.get("state") in SAFE_STATES:
            print("Codespace already started. Use restart for a fresh session.")
            return report(current, operation)
        if current:
            current = api("POST", "/user/codespaces/" + current["name"] + "/start")
        else:
            current = api("POST", "/repos/" + REPO + "/codespaces", {
                "ref": "main",
                "display_name": DISPLAY_NAME,
                "devcontainer_path": ".devcontainer/devcontainer.json",
                "idle_timeout_minutes": 180,
                "retention_period_minutes": 60,
            })
        return report(current, operation)
    if operation == "stop":
        if not current:
            return report(None, operation)
        if current.get("state") in SAFE_STATES:
            current = api("POST", "/user/codespaces/" + current["name"] + "/stop")
        return report(current, operation)
    if operation == "restart":
        if not current:
            current = api("POST", "/repos/" + REPO + "/codespaces", {
                "ref": "main",
                "display_name": DISPLAY_NAME,
                "devcontainer_path": ".devcontainer/devcontainer.json",
                "idle_timeout_minutes": 180,
                "retention_period_minutes": 60,
            })
            return report(current, operation)
        if current.get("state") in SAFE_STATES:
            api("POST", "/user/codespaces/" + current["name"] + "/stop")
            # Wait for complete shutdown before restarting; never guess.
            for _ in range(30):
                time.sleep(2)
                state = api("GET", "/user/codespaces/" + current["name"])
                if state.get("state") in ("Shutdown", "Stopped"):
                    break
            else:
                raise RuntimeError("Codespace did not shut down; refusing restart")
        current = api("POST", "/user/codespaces/" + current["name"] + "/start")
        return report(current, operation)

if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, KeyError, OSError) as exc:
        print("Black Cat DNS control failed: " + str(exc), file=sys.stderr)
        sys.exit(1)
