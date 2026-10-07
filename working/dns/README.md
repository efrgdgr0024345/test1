# Black Cat temporary DNS consensus service

This folder contains a temporary DNS-over-HTTPS service intended to run for 1, 2, or 3 hours in a GitHub Codespace.

## What it does

1. Firefox sends a DNS query to the temporary `/working/dns` DoH endpoint.
2. The service asks every configured upstream resolver over **DNS-over-HTTPS only**.
3. Responses are normalized before comparison. TTL, packet ordering, DNSSEC signature timing material, and letter case do not create false mismatches.
4. For A/AAAA address lookups, **every configured resolver must return the same normalized result**. There is no majority vote.
5. Any disagreement or resolver failure is fail-closed: the DoH reply is SERVFAIL and no address is released.
6. The dashboard stores a RAM-only evidence report for up to 10 minutes.
7. The optional Firefox helper sees a main-frame DNS failure, re-checks the hostname, and redirects the tab to the evidence page when the status is `mismatch` or `unavailable`.

## Current independent resolver set

The committed configuration uses:

- UncensoredDNS unicast — Copenhagen, Denmark — no plaintext DNS dependency.
- dnsforge Blank — Germany — the operator's no-filter profile.
- Digitale Gesellschaft — Switzerland.

Their HTTPS hostnames are connected using committed bootstrap IPs while TLS certificate validation is still performed against the real resolver hostname. Upstream HTTP redirects are never followed.

This is **multi-resolver consensus**, not a claim that the three queries originate from three continents. A DNSChecker-style global propagation network would require geographically distributed probe machines. The resolver list is deliberately explicit so more independent encrypted resolvers can be added after their endpoint, filtering policy, and bootstrap address are verified.

## HTTPS-only public transport

GitHub Codespaces gives a public forwarded port an address like:

`https://<codespace>-8080.app.github.dev`

The application backend binds **only to 127.0.0.1:8080**, so there is no directly Internet-reachable plaintext socket. GitHub's edge is the Internet-facing HTTPS endpoint.

Do not change the Codespaces forwarded-port protocol to "HTTPS". GitHub documents that changing a public forwarded port to HTTPS protocol automatically makes it private. The default forwarding protocol is therefore intentionally used behind GitHub's external HTTPS endpoint.

`verify.sh` refuses to mark a session verified unless:

- the public HTTPS dashboard is reachable using TLS 1.2 or newer;
- public plain HTTP either fails or redirects to HTTPS rather than serving application content; and
- a real RFC 8484 DNS message round-trip succeeds through the public HTTPS DoH URL.

## Start a 1–3 hour session

Create a Codespace from branch `black-cat-doh`. The devcontainer installs dependencies and starts the loopback service automatically.

Choose a lifetime before restarting the service if desired:

```bash
export LIFETIME_SECONDS=3600   # or 7200 / 10800
bash working/dns/start.sh
```

Then explicitly expose and verify the temporary endpoint:

```bash
bash working/dns/make-public.sh
```

On success it prints the exact dashboard and DoH capability URLs and writes them to:

`working/dns/.runtime/session.json`

The important endpoint ends in:

`/s/<random-session-token>/working/dns`

The random token is generated at runtime and is never committed.

## Firefox

Configure Firefox to use the printed DoH URL and use its strongest DoH-only/no-fallback mode. If Firefox is allowed to fall back to the operating system resolver, a disagreement can be bypassed by that fallback.

To get the requested mismatch report redirection during this temporary experiment:

1. Open `about:debugging#/runtime/this-firefox`.
2. Choose **Load Temporary Add-on**.
3. Select `working/dns/firefox/manifest.json`.
4. Open the add-on preferences and paste the printed dashboard URL.
5. Keep the add-on temporary; Firefox removes it when that profile/session ends.

The helper does **not** manufacture a replacement IP. It redirects only after the navigation has already failed DNS resolution and the consensus service independently reports `mismatch` or `unavailable`.

## Security / interpretation

- Agreement is consistency evidence, not proof that an IP is benign or authentic.
- Different DNS answers are often legitimate for CDNs and geo-routing. This strict mode will intentionally block those cases.
- DNSSEC AD is reported by the upstreams. The current implementation does not independently validate the full DNSSEC chain.
- Resolver operator location labels are descriptive; this does not claim the query was observed from a measurement probe at that location.
- Reports and cache live in memory only.
- Session lifetime is capped at three hours.
- The public URL is a capability URL. Do not publish it while the session is active.

## Tests

GitHub Actions runs syntax and consensus-policy unit tests on this branch. Locally:

```bash
cd working/dns
.venv/bin/python tests.py
```
