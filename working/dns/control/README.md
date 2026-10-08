# Black Cat DNS: cloud chat controller v2

Project: https://github.com/efrgdgr0024345/test1/tree/main/working/dns

This is the cloud-control layer, not a replacement DNS implementation. The
existing resolver comparison, HTTPS verification, dashboard and Firefox helper
are preserved. The DNS process runs in Codespaces. Commands run on GitHub-hosted
Actions runners; nothing here requires a DNS process on the user's computer.

## Current status and one-time authorisation

The control preflight on 8 October 2026 found that the Actions secret
`BLACKCAT_CODESPACES_PAT` was missing:
https://github.com/efrgdgr0024345/test1/actions/runs/37709946965

A missing credential is an authentication blocker, not a successful deployment.
No live DNS endpoint has been confirmed by this controller at this point.

Create a short-lived fine-grained PAT owned by `efrgdgr0024345`, restricted to
`test1`, then save it under repository Settings > Secrets and variables > Actions:
https://github.com/efrgdgr0024345/test1/settings/secrets/actions

Use the name `BLACKCAT_CODESPACES_PAT`. Never paste it into chat, source, an issue,
or the request file. Documented REST permissions are Codespaces read/write,
Codespaces lifecycle admin read/write, and Codespaces metadata read (to select a
small machine when creation is necessary). CLI SSH/port authorisation must also
be tested with the credential. Do not grant unrelated permissions to mask an
unexplained authentication failure.

The SSH feature has been added to the devcontainer. An older Codespace built
before that change may lack an SSH server. The controller fails safely rather
than deleting it, rebuilding over unknown local changes, or creating duplicates.
Updating/rebuilding that old devcontainer can require a one-time GitHub UI action.

## Chat control procedure

The requesting chat runtime generates a fresh RSA-3072 reply key pair. Only the
PUBLIC key enters `working/dns/control/request.json`. The private key stays in the
requesting cloud runtime and must not be printed, uploaded or committed.

A version-2 request contains:

- operation: `start`, `status`, `stop`, or `restart`;
- request_id: fresh 32-character lowercase hexadecimal ID;
- lifetime_seconds: 3600, 7200 or 10800 (default choice is one hour);
- issued_at and valid_until: UTC epoch seconds; command validity at most one hour;
- reply_public_key: public RSA PEM, 3072 or 4096 bits;
- optional codespace: exact existing machine name to disambiguate.

Updating only this file on `main` triggers **Black Cat DNS Chat Control**. Requests
from forks, PR events, non-main refs, or actors other than the configured owner do
not receive the credential through this workflow. Successful code tests alone
never constitute a live deployment.

The controller discovers this repository's machine, or chooses an available
2-core machine if none exists. It does not silently choose a larger machine.
It waits for Available, connects over GitHub-authenticated SSH, and updates a
clean worktree by fast-forward only to the workflow commit. It refuses dirty or
divergent worktrees. It never runs git reset/clean, force checkout or Codespace
DELETE operations. Stopped storage is preserved and can still incur charges.

Repeated start returns an existing live session without changing its expiry.
Replaying the same restart request does not extend the session. A consumed
request cannot start a new session after its old session ended. A NEW restart
request intentionally replaces the old DNS session and invalidates its URL.
Status does not start a stopped machine. A legacy un-managed running service is
not silently renewed by start; a deliberate restart migrates it.

## Exact live URL and encrypted handback

After publication, the Actions runner performs the existing public HTTPS
acceptance tests without GitHub browser cookies. GET and POST DNS messages must
return positive IPv4/IPv6 answers. All configured providers must be represented
and agree. Plain HTTP must refuse a connection or strictly redirect to the same
HTTPS route; a timeout is not counted as proof. Failure rolls back a machine
started or modified by this request and never advertises a working URL.

The real dashboard URL, full `/working/dns` URL, absolute expiry, running commit
and verification results are encrypted with a fresh AES-256-GCM key. RSA-OAEP with
SHA-256 wraps that AES key. The request ID is bound into both operations. Public
workflow logs receive only:

`BLACKCAT_ENCRYPTED_RESULT=<base64 envelope>`

The chat reads the log from the exact authenticated workflow run and commit,
decrypts it with its private reply key using `protocol.unseal`, validates the
request ID and returned service URL, and gives the user the actual address.
Encryption does not by itself authenticate a publisher: checking the GitHub run,
repository, commit, actor and request ID remains mandatory.

If a chat runtime loses its private key, issue a new status request with a new key.
Never try to recover an old reply by weakening encryption. The private key is not
needed by the DNS server and is never installed in the Codespace.

## Session deadline and compute cleanup

`managed_server.py` wraps the existing DNS Engine and loopback server. Its absolute
lease is written to `.runtime/managed-lease.json`. Remaining time is recomputed
from that deadline, never reset by a reboot. Ordinary Codespace boot no longer
publishes a new default three-hour session; it waits for a chat command. An expired
lease cannot restart DNS. The DNS child receives a minimal environment, without
GitHub credentials or unrelated Codespaces secrets.

The machine display name records a nonsecret management tag and expiry. A separate
**Black Cat DNS Expiry Cleanup** workflow checks every ten minutes, stops ONLY
expired machines carrying that tag in this repository, and confirms Shutdown.
GitHub schedules can be delayed, so this is not an exact compute-stop guarantee.
The DNS process has its own hard lifetime independently of that cleanup schedule.
A missing/revoked token or GitHub outage can prevent machine shutdown; failed stop
confirmation is reported, never hidden. Stopped machines are not deleted.

## HTTPS boundaries and remaining client testing

Public TLS terminates at GitHub's Codespaces edge. Our backend is HTTP bound to
127.0.0.1 only. This is not uninterrupted TLS into the Python process. Upstream
resolver queries remain verified HTTPS/HTTP2 with pinned bootstrap IPs.

Clients must support a custom DoH URL, prevent plaintext/system-DNS fallback,
and be able to bootstrap the service hostname. Different legitimate CDN answers
can trigger this deliberately strict policy. DNS failure by itself cannot open a
page in every app; automatic evidence-page navigation still needs the Firefox
helper or equivalent app integration. Actual device bootstrap and Firefox helper
behavior require client-side validation; server tests do not prove them.

## Tests

CI installs both DNS and controller requirements and runs all `test*.py` files.
New controller tests cover command windows, replay, selection, workspace safety,
reply encryption/tampering, fixed deadlines and cleanup targeting. Real local TLS
integration tests use controlled upstream replies to exercise positive DNS,
certificate rejection, HTTP rejection, disagreement reports, upstream timeout,
capability access and expiry. These local TLS tests are not a claim that a public
Codespace is deployed. Existing live upstream probes remain in CI.

Primary references:
- https://docs.github.com/en/rest/codespaces/codespaces
- https://cli.github.com/manual/gh_codespace_ssh
- https://docs.github.com/en/codespaces/developing-in-a-codespace/forwarding-ports-in-your-codespace
- https://cryptography.io/en/latest/hazmat/primitives/asymmetric/rsa/
- https://cryptography.io/en/latest/hazmat/primitives/aead/
