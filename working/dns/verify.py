#!/usr/bin/env python3
"""Verify one running public session; never confuse readiness with deployment."""
from __future__ import annotations
import base64
import datetime as dt
import http.client
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urljoin, urlsplit

import dns.message
from smoke import https_url, request, run

ROOT = Path(__file__).resolve().parent
SESSION = ROOT / '.runtime/session.json'


def save(value: dict) -> None:
    fd, temp = tempfile.mkstemp(prefix='session-', dir=SESSION.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(value, out, indent=2)
        os.replace(temp, SESSION)
    finally:
        Path(temp).unlink(missing_ok=True)


def redirect_is_https(original: str, location: str | None) -> bool:
    if not location:
        return False
    old = urlsplit(original)
    target = urlsplit(urljoin(original, location))
    same_path = target.path == old.path
    # Measured Codespaces HTTP 308 behavior strips one trailing slash from
    # the session landing path. This is not a DNS route or origin change.
    # Keep DoH paths, hostname, TLS port, credentials, query and fragment strict.
    if re.fullmatch(r'/s/[A-Za-z0-9_-]+/', old.path):
        same_path = same_path or target.path == old.path[:-1]
    return (target.scheme == 'https' and target.hostname == old.hostname
            and target.port in (None, 443) and target.username is None
            and target.password is None and same_path
            and target.query == old.query and not target.fragment)


def reject_http(url: str, body: bytes | None = None) -> str:
    """Send only a public test-domain query. A timeout is inconclusive, not a pass."""
    https_url(url)
    u = urlsplit(url)
    parts = u.path.split('/')
    if len(parts) < 4 or parts[1] != 's':
        raise ValueError('Unexpected session path for plaintext transport probe')
    parts[2] = 'invalid-transport-probe'
    u = u._replace(path='/'.join(parts))
    url = u.geturl()
    target = u.path or '/'
    if u.query:
        target += '?' + u.query
    conn = http.client.HTTPConnection(u.hostname, 80, timeout=12)
    try:
        conn.request('POST' if body is not None else 'GET', target, body=body,
                     headers={'Content-Type': 'application/dns-message', 'Connection': 'close'})
        res = conn.getresponse()
        media = res.getheader('Content-Type', '').split(';')[0].lower().strip()
        if media == 'application/dns-message':
            raise ValueError('FAIL: public plaintext HTTP returned a DNS message')
        if res.status not in (301, 302, 303, 307, 308):
            raise ValueError('Plain HTTP did not refuse connection or strictly redirect to HTTPS')
        if not redirect_is_https(url, res.getheader('Location')):
            raise ValueError('Plain HTTP redirected to a different or insecure destination')
        return 'redirects to the same HTTPS origin and route (dashboard trailing slash may be normalized)'
    except ConnectionRefusedError:
        return 'TCP port 80 refused the connection'
    finally:
        conn.close()


def dashboard_document(url: str) -> dict:
    """Check both browser negotiation and the actual public application HTML.

    The forwarding service may show a first-visit anti-phishing page when
    Accept includes text/html. A non-browser Accept header is a documented
    content-negotiation alternative, not authentication. The notice alone NEVER
    passes: our actual page must still be obtained over verified TLS without
    cookies, credentials or redirect following. DoH requests are unchanged.
    Reference: https://learn.microsoft.com/en-us/azure/developer/dev-tunnels/security
    """
    def ours(body):
        return b'Black Cat DNS Consensus' in body and b'id="endpoint"' in body
    html = request(url, kind='text/html')
    if ours(html):
        return {'browser_first_visit_notice': False, 'dashboard_verified': True}
    title = re.search(br'<title[^>]*>(.*?)</title>', html, re.I | re.S)
    title = re.sub(r'\s+', ' ', title.group(1).decode(errors='replace'))[:160] if title else 'untitled forwarding page'
    actual = request(url, kind='text/html', accept='*/*')
    if not ours(actual):
        raise ValueError('Not our dashboard; a proxy, login or notice page cannot pass')
    return {'browser_first_visit_notice': True, 'browser_first_page_title': title,
            'dashboard_verified': True,
            'dashboard_check': 'Actual HTML fetched with Accept */*; no cookies, authentication or redirects'}


def main() -> None:
    session = json.loads(SESSION.read_text())
    session['deployment_verified'] = False
    session.pop('verification', None)
    save(session)
    dashboard, doh = session['dashboard'], session['doh']
    if doh != dashboard.rstrip('/') + '/working/dns':
        raise ValueError('Dashboard and DoH URLs do not belong to the same session')
    print('Checking the actual public HTTPS dashboard (no login cookies)...', flush=True)
    dashboard_evidence = dashboard_document(dashboard)
    name = os.environ.get('VERIFY_NAME', 'unicast.uncensoreddns.org.')
    wire = dns.message.make_query(name, 'A').to_wire()
    encoded = base64.urlsafe_b64encode(wire).rstrip(b'=').decode('ascii')
    print('Checking plaintext HTTP on the dashboard, DoH GET and DoH POST...', flush=True)
    http_checks = [reject_http(dashboard), reject_http(doh + '?dns=' + encoded),
                   reject_http(doh, body=wire)]
    print('Checking three-resolver consensus through the public HTTPS API...', flush=True)
    providers = {r['name'] for r in json.loads((ROOT / 'resolvers.json').read_text())}
    report = json.loads(request(dashboard.rstrip('/') + '/api/check',
                               body=json.dumps({'name': name}).encode(), kind='application/json'))
    if report.get('status') != 'match' or report.get('allowed') is not True:
        raise ValueError('Live resolvers did not reach unanimous positive consensus')
    groups = report.get('comparisons', [])
    if len(groups) != 2 or {g.get('qtype') for g in groups} != {'A', 'AAAA'}:
        raise ValueError('Both IPv4 and IPv6 evidence are required')
    for group in groups:
        rows = group.get('rows', [])
        if (group.get('status') != 'match' or len(rows) != len(providers)
                or {r.get('provider') for r in rows} != providers
                or any(r.get('error') or r.get('rcode') != 'NOERROR' or not r.get('ips') for r in rows)
                or len({tuple(sorted(r['ips'])) for r in rows}) != 1):
            raise ValueError('Resolver evidence is incomplete or disagrees')
    print('Checking successful DNS-over-HTTPS GET and POST for IPv4 and IPv6...', flush=True)
    addresses = run(doh, name)
    current = json.loads(SESSION.read_text())
    if current['doh'] != doh:
        raise ValueError('The session changed during verification')
    current['deployment_verified'] = True
    current['verification'] = {'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                               'test_name': name, 'addresses': addresses,
                               'http_checks': http_checks, 'dashboard': dashboard_evidence,
                               'coverage': 'live transport and positive consensus; not a full security audit'}
    save(current)
    print('\nLIVE HTTPS ACCEPTANCE PASSED')
    print('Dashboard:', dashboard)
    print('DoH:', doh)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        detail = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        raise SystemExit('Deployment acceptance FAILED: ' + detail
                         + '. Session remains unverified; no success URL is advertised.')
