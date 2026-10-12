# Black Cat temporary DNS consensus

Repository: https://github.com/efrgdgr0024345/test1

DNS source: https://github.com/efrgdgr0024345/test1/tree/main/working/dns

Cloud control guide: https://github.com/efrgdgr0024345/test1/tree/main/working/dns/control

## Verified live deployment — 12 October 2026

The first complete public HTTPS deployment passed on **12 October 2026 at 05:26:10 UTC**.

Deployment run: https://github.com/efrgdgr0024345/test1/actions/runs/38207855261

Regression and live-upstream test run: https://github.com/efrgdgr0024345/test1/actions/runs/38207855216

Verified running code: `0690c33d8257bb2c1353b301b738e2c9da4122ca`.

This records a successful temporary session, **not a claim that this service is always online**. The actual session URLs and expiry are returned privately to the requesting chat. Never publish the usable capability URL or a private reply key in this repository.

The missing-token and old-container SSH blockers are resolved. The original pre-SSH Codespace was preserved stopped, not rebuilt or deleted. A fresh two-core Codespace with the committed SSH feature now runs the service.

## Use from ChatGPT

Ask to start DNS for one, two or three hours, check DNS status, stop DNS, or restart DNS. The connected chat submits a validated request on `main`; GitHub Actions controls the Codespace and tests its actual public HTTPS endpoint. The result, including the complete `/working/dns` address, is encrypted to that request's public key and retrieved by the requesting chat.

The controller and DNS process run in GitHub's cloud. Nothing here requires a DNS process on the user's laptop. The optional Firefox helper runs in the client browser and is separate from server hosting.

The repository Actions secret is `BLACKCAT_CODESPACES_PAT`. It is configured in GitHub, not in chat or source code. Do not replace or broaden an existing working token unnecessarily.

## Acceptance evidence

The successful public deployment verified:

- Real dashboard HTML over certificate-validated HTTPS, with no login cookies or GitHub authentication.
- Positive standard DoH GET and POST for both A and AAAA, using ordinary `application/dns-message` requests and no tunnel-specific headers.
- Unanimous positive answers from every configured resolver through the public comparison API.
- Plain HTTP receives HTTP 308 upgrades to the same HTTPS origin. The edge normalizes one trailing slash on the dashboard landing path; DoH path and query remain exact.
- No actual session capability is sent in plaintext probes. Timeouts, login pages, empty answers, SERVFAIL and NXDOMAIN do not count as successful positive checks.

A browser's first visit may display **Codespaces Access Port**, GitHub's forwarding warning. The verifier checks the actual application HTML separately using non-browser content negotiation; the notice alone never passes. Standard DoH GET/POST was tested without notice-bypass headers or cookies.

Public HTTPS terminates at GitHub's forwarding edge. The application backend is HTTP on `127.0.0.1:8080`; this is not uninterrupted TLS into Python. Upstream queries use verified HTTPS/HTTP2 with pinned bootstrap IPs.

## Policy and lifecycle

All configured resolvers must agree. A disagreement or missing result fails closed. Legitimate geographic/CDN DNS differences can therefore cause blocks. Three resolver operators are compared; this is not a global DNSChecker-style distributed probe network or proof that an IP is safe.

A repeated start preserves the live session and its expiry. A new restart replaces it. Status does not start a stopped machine. Every managed session has an absolute deadline; rebooting does not renew it. DNS stops serving at expiry independently of the scheduled cloud-machine cleanup. GitHub schedules may run late, so exact compute-stop timing is not promised. Stopped machines retain storage and are not deleted automatically.

Server-side controlled tests cover mismatch reports, timeout blocking, TLS rejection, capability protection and expiry. Actual client bootstrap and automatic Firefox-helper navigation still require testing on the user's device. DNS failure alone cannot redirect every application to a web page.

The older `working/dns/README.md`, `launch.sh` and `make-public.sh` describe a manual fallback, not the normal chat-controlled lifecycle. Prefer the current controller guide above.
