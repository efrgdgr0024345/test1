# Black Cat temporary DNS consensus

Source: [working/dns](working/dns). This repository is NOT itself a live DNS endpoint.

## Automatic Codespaces launch

Create a Codespace from `main`: https://codespaces.new/efrgdgr0024345/test1?ref=main

The devcontainer installs the dependencies and GitHub CLI, then runs `working/dns/launch.sh`. After GitHub authorizes the Codespace, that script starts the loopback backend, requests a public forwarded port, and runs strict live verification automatically. No separate terminal command should be needed in the normal path.

Only after verification passes does it print the exact dashboard URL and the **DoH URL to paste into an app**. They are also in `working/dns/.runtime/session.json`. These URLs contain a private session capability and must not be committed to the repository.

If the launch fails, it attempts to return the port to private and stops the backend. A success URL is not advertised. Service lifetime defaults to three hours; stopping the DNS process does not itself delete the Codespace or guarantee that billing has stopped.

## What live verification requires

- Actual public HTTPS dashboard content, without login cookies or a GitHub token.
- Certificate validation and TLS 1.2 or later, with no HTTPS redirect following.
- HTTP transport probes must be refused or redirect to the same HTTPS route. Timeouts are inconclusive and fail the check. These probes use an INVALID session token so the real token is never transmitted in plaintext.
- Successful unanimous A and AAAA results from every configured resolver through the public comparison API.
- Successful DNS-over-HTTPS GET and POST returning non-empty matching address sets.
- SERVFAIL, NXDOMAIN on the positive test domain, empty answers, login pages, mismatched responses and truncated packets must fail verification.

Unit tests and the GitHub Actions live upstream probe are NOT proof that a Codespace has been deployed. The live acceptance script must run against that Codespace's actual public endpoint. Browser-helper redirection still needs an end-to-end Firefox test; it is not covered by these unit tests.

## Existing technical notes

See [working/dns/README.md](working/dns/README.md) for the resolver policy, report UI, and Firefox helper. Its older manual launch commands remain compatible, but `main` now starts publication and verification automatically.

GitHub public HTTPS terminates at its forwarding edge. The internal application binds HTTP to loopback only. This is public HTTPS-only access, not a claim of HTTPS on every internal hop.

References: https://docs.github.com/en/codespaces/developing-in-a-codespace/forwarding-ports-in-your-codespace and https://docs.github.com/en/rest/codespaces/codespaces
