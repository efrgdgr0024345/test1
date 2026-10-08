# Black Cat temporary DNS consensus

Repository: https://github.com/efrgdgr0024345/test1

DNS source: https://github.com/efrgdgr0024345/test1/tree/main/working/dns

Cloud controller and current setup guide:
https://github.com/efrgdgr0024345/test1/tree/main/working/dns/control

**This repository is source code, not a live DNS URL.** The complete session URL
is generated at runtime and handed back encrypted to the requesting chat.

## Current cloud-control path

Ask ChatGPT to start DNS for one, two or three hours. It writes a short-lived,
validated request on `main`; GitHub Actions controls the Codespace, verifies the
public HTTPS service, and emits an encrypted reply containing the exact app URL.
ChatGPT decrypts that reply in its cloud runtime. No DNS process runs on your PC.

The one-time Actions secret is `BLACKCAT_CODESPACES_PAT`:
https://github.com/efrgdgr0024345/test1/settings/secrets/actions

The access preflight found this secret missing. Until authorisation and live
acceptance pass, there is no confirmed working public endpoint from this controller.
Preflight: https://github.com/efrgdgr0024345/test1/actions/runs/37709946965

Version-2 source commit: `b9118649b84559edfcb4d35bf33002f1b980a0b4`.
Passed regression/TLS tests and live upstream probe:
https://github.com/efrgdgr0024345/test1/actions/runs/37711506059

See the controller guide for least-privilege token permissions, SSH prerequisites,
command fields, encrypted replies, fixed deadlines, and handling an older Codespace.

## Startup and shutdown behavior

The devcontainer includes GitHub CLI and an SSH-server feature. Its boot hook now
prepares for CHAT CONTROL; it does not automatically publish a fresh three-hour
DNS session on every boot. An older Codespace may need a one-time update/rebuild
for the SSH feature. The controller refuses to overwrite dirty work or delete a
machine to work around that problem.

A repeated start preserves the current live session. A new restart intentionally
replaces it. Status does not start a stopped machine. Each managed session has an
absolute deadline; rebooting does not renew it. The process expires on its own.
A separate scheduled cleanup stops expired managed Codespaces and confirms their
state. GitHub schedules may run late, so exact compute-stop timing is not promised.
Stopped machines retain storage and are not automatically deleted by this code.

## What qualifies as live

The real public dashboard must load without login cookies. Certificate verification
and positive DoH GET/POST tests must pass for IPv4 and IPv6. Every configured
resolver must be represented and agree. Plain HTTP must be refused or strictly
redirected to the same HTTPS route; a timeout is not treated as proof. Error DNS
replies, login pages and empty answers cannot pass positive acceptance.

Public HTTPS terminates at GitHub's forwarding edge. The application backend is
HTTP bound to loopback only; this is not uninterrupted TLS into Python. Upstream
queries use verified HTTPS/HTTP2 with pinned bootstrap IPs.

Local TLS integration tests exercise disagreement, timeout, invalid certificate,
plaintext rejection, access tokens and expiry. They are NOT a public Codespace
deployment. Actual client bootstrap and Firefox redirection still require device
validation. Clients must support a custom DoH URL and avoid silent DNS fallback.

## Technical notes and manual fallback

Resolver policy, dashboard and Firefox files are in `working/dns`. The older
`working/dns/README.md`, `launch.sh` and `make-public.sh` describe a MANUAL fallback,
not the normal chat-controlled lifecycle. Prefer the v2 controller guide linked above.
Keep session URLs and all private keys out of public source, issues and logs.
