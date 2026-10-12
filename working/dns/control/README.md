# Black Cat DNS: cloud chat controller v2

Project: https://github.com/efrgdgr0024345/test1/tree/main/working/dns

## Verified deployment and current operating path

The complete public HTTPS deployment passed on **12 October 2026 at 05:26:10 UTC**:
https://github.com/efrgdgr0024345/test1/actions/runs/38207855261

Verified running code: `0690c33d8257bb2c1353b301b738e2c9da4122ca`.
Regression suite and live upstream probe:
https://github.com/efrgdgr0024345/test1/actions/runs/38207855216

The Actions secret is now present and works for starting/stopping, SSH and port publication. The original Codespace lacked sshd; it was preserved stopped. A fresh two-core Codespace with the committed SSH feature was created, and its real public DNS endpoint passed acceptance. This is evidence of a temporary session, not perpetual uptime. Obtain a current private session URL through a fresh chat status/start request.

The active workflow entry point is `acceptance_diagnostics.py`, which wraps the standard controller with redacted encrypted diagnostics. The one-time `recover_runtime.py` migration is retained as history and tests, not executed by normal start/status/stop/restart requests.

## One-time authorisation for a new installation

Save a short-lived GitHub token as the repository Actions secret `BLACKCAT_CODESPACES_PAT`:
https://github.com/efrgdgr0024345/test1/settings/secrets/actions

Never put the token in chat, source, an issue, a request file, or a public log. Start from repository-restricted access. Documented lifecycle permissions are Codespaces read/write and Codespaces lifecycle admin read/write. Codespaces metadata read is needed when selecting a new machine through the catalog endpoint. CLI SSH and port permissions must be verified with a real operation. Do not grant unrelated permissions to hide unexplained failures.

The current installation already has a working token and runtime; do not repeat token setup without evidence of a new authorisation failure. Do not delete/rebuild an old machine over unknown work. The recovery procedure preserved the original and reused its authenticated two-core machine metadata after machine-catalog access was denied.

## Chat command procedure

The requesting chat runtime generates a fresh RSA-3072 reply key pair. Only the PUBLIC key enters `working/dns/control/request.json`; the private key remains in that runtime and must never be printed, uploaded or committed.

A version-2 request contains:

- `operation`: start, status, stop or restart;
- `request_id`: fresh 32-character lowercase hexadecimal ID;
- `lifetime_seconds`: 3600, 7200 or 10800;
- `issued_at` and `valid_until`: UTC epoch seconds, validity at most one hour;
- `reply_public_key`: RSA public PEM, 3072 or 4096 bits;
- optional `codespace`: exact target name to disambiguate.

Updating the request on main triggers **Black Cat DNS Chat Control**. The secret-bearing job is restricted to this repository, main, and the configured owner actor, not fork or PR code. Dependencies and regression tests run before the credential-bearing step.

The controller verifies ownership, waits for Available, and connects using GitHub-authenticated SSH. It fast-forwards a clean workspace to the exact workflow commit and refuses dirty or divergent worktrees. It never uses git reset/clean, forced checkout, or Codespace deletion. The PAT is not installed in the DNS process.

Repeated start returns the same live session without extending its expiry. A new restart intentionally invalidates the previous session. Replaying a consumed request cannot renew an ended session. Status does not start a stopped machine. Status on a live machine rechecks public HTTPS without changing its lease or running code. The workflow commit can therefore differ from the preserved running code commit during a status request.

## Private URL handback

After publication, the Actions runner tests the real public service without GitHub login cookies. Positive A and AAAA DoH GET/POST must succeed; all configured resolvers must be represented and agree. Plain HTTP must refuse or upgrade to the same HTTPS origin and DNS route, preserving the query. Only the measured dashboard landing-path trailing-slash normalization is allowed. Timeouts, SERVFAIL, NXDOMAIN on the positive test, empty answers and generic pages do not pass.

The public forwarding service can display a first-visit **Codespaces Access Port** notice when Accept requests HTML. The verifier records that fact and separately fetches the real dashboard with Accept */*, still checking its exact expected markers and response MIME. The notice alone never qualifies. Standard DNS requests continue to use application/dns-message with no browser cookies, tunnel-authentication or notice-bypass headers.

The session URL, dashboard, absolute expiry, running commit, verification and bounded diagnostics are encrypted with AES-256-GCM. RSA-OAEP-SHA256 wraps the random AES key. Both bind the request ID as authenticated context. Public output contains only `BLACKCAT_ENCRYPTED_RESULT=<base64 envelope>`. The workflow also retains `blackcat-encrypted-result`, an artifact containing only result.enc.json, for one day.

The chat verifies the authenticated run's repository, actor, commit and request ID; downloads the artifact; checks its GitHub-reported SHA-256; decrypts using its private key and `protocol.unseal`; checks the result binding and session URL; and gives the user the actual URL. Encryption alone does not authenticate the publisher. The private key must never be sent to GitHub or the Codespace.

If the requesting runtime loses the private key, generate a new key and issue status. Do not weaken encryption or publish a live capability to recover an old response.

## Deadline and cleanup

`managed_server.py` starts the DNS core with an absolute lease stored privately in `.runtime/managed-lease.json`. Remaining time is recomputed from that deadline, not reset on reboot. The boot hook does not automatically publish a new three-hour session. The DNS child receives a minimal environment without controller credentials or unrelated Codespaces secrets.

A nonsecret expiry tag in the machine display name is used by **Black Cat DNS Expiry Cleanup**, scheduled every ten minutes. It targets only expired managed instances in this repository and confirms Shutdown. GitHub schedules can be delayed and revoked credentials/outages can prevent compute shutdown; exact compute-stop timing is not guaranteed. DNS stops serving independently at its deadline. Failed shutdown confirmation is reported, not hidden. Stopped machines retain storage and are not deleted.

## Scope and remaining client validation

DNS executes in GitHub Codespaces; commands execute in GitHub-hosted Actions. No server Python, VM or DNS process is required on the user's device. A browser still executes its normal web-interface JavaScript, and the optional Firefox helper executes locally if installed.

Public TLS terminates at GitHub's forwarding edge; our backend is HTTP bound only to 127.0.0.1:8080. Upstream queries are verified HTTPS/HTTP2 with pinned bootstrap IPs. This is not uninterrupted TLS into Python, a worldwide probe network, or proof that matching answers are authentic. Legitimate CDN/geographic answers can differ and be blocked by the strict policy.

Clients need custom DoH support, no silent system-DNS fallback, and a usable bootstrap path for the service hostname. DNS failure cannot itself navigate every app to a report page. The Firefox helper is implemented, but real device bootstrap and automatic browser navigation remain separate client-side tests.

Regression tests cover control windows/replay, workspace safety, encryption/tampering, deadlines, targeted cleanup, controlled TLS positive/mismatch/timeout responses, invalid certificates, plaintext rejection, capability checks, encrypted diagnostics, dashboard negotiation, and precise HTTPS redirects. Controlled tests are distinct from the actual public deployment run linked above.

Primary references:
- https://docs.github.com/en/rest/codespaces/codespaces
- https://cli.github.com/manual/gh_codespace_ssh
- https://docs.github.com/en/codespaces/developing-in-a-codespace/forwarding-ports-in-your-codespace
- https://learn.microsoft.com/en-us/azure/developer/dev-tunnels/security
- https://cryptography.io/en/latest/hazmat/primitives/asymmetric/rsa/
- https://cryptography.io/en/latest/hazmat/primitives/aead/
