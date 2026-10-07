#!/usr/bin/env python3
"""Strict live DoH acceptance test. A failed lookup is NEVER a passing test."""
from __future__ import annotations
import base64
import ipaddress
import os
import ssl
import urllib.error
import urllib.request
from urllib.parse import urlsplit

import dns.flags
import dns.message
import dns.rcode
import dns.rdatatype

MAX_BODY = 1024 * 1024

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def https_url(url: str) -> str:
    u = urlsplit(url)
    if (u.scheme != 'https' or not u.hostname or u.username is not None
            or u.password is not None or u.fragment or u.port not in (None, 443)):
        raise ValueError('An HTTPS URL on port 443 without credentials is required')
    return url


def request(url: str, *, body: bytes | None = None,
            kind: str = 'application/dns-message', maximum: int = MAX_BODY):
    https_url(url)
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    # No environment proxies, cookies, redirect following, or unverified TLS.
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=context), NoRedirect())
    headers = {'Accept': kind, 'User-Agent': 'BlackCat-DoH-Acceptance/0.2'}
    if body is not None:
        headers['Content-Type'] = kind
    req = urllib.request.Request(url, data=body, headers=headers,
                                 method='GET' if body is None else 'POST')
    try:
        with opener.open(req, timeout=30) as response:
            if response.status != 200:
                raise ValueError('HTTPS response was not 200')
            if response.headers.get_content_type() != kind:
                raise ValueError('Wrong response content type; login/interstitial pages do not pass')
            result = response.read(maximum + 1)
            if len(result) > maximum:
                raise ValueError('Response exceeds size limit')
            return result
    except urllib.error.HTTPError as exc:
        # Do not print the capability URL carried in urllib exceptions.
        raise ValueError(f'HTTPS endpoint returned HTTP {exc.code}; redirects are not followed') from None
    except urllib.error.URLError as exc:
        raise ValueError(f'HTTPS connection failed: {type(exc.reason).__name__}') from None


def validate_answer(query: dns.message.Message, wire: bytes) -> list[str]:
    answer = dns.message.from_wire(wire, ignore_trailing=False)
    if not query.is_response(answer) or answer.flags & dns.flags.TC:
        raise ValueError('Mismatched or truncated DNS response')
    if answer.rcode() != dns.rcode.NOERROR:
        raise ValueError('Positive DNS check failed: ' + dns.rcode.to_text(answer.rcode()))
    wanted = query.question[0].rdtype
    ips = sorted({str(ipaddress.ip_address(rr.address))
                  for rrset in answer.answer if rrset.rdtype == wanted
                  for rr in rrset})
    if not ips:
        raise ValueError('Positive DNS check returned no requested IP addresses')
    return ips


def run(url: str, name: str = 'unicast.uncensoreddns.org.') -> dict:
    https_url(url)
    if urlsplit(url).query:
        raise ValueError('The base DoH URL must not include query parameters')
    evidence = {}
    for qtype in ('A', 'AAAA'):
        query = dns.message.make_query(name, qtype, want_dnssec=True)
        wire = query.to_wire()
        encoded = base64.urlsafe_b64encode(wire).rstrip(b'=').decode('ascii')
        post = validate_answer(query, request(url, body=wire, maximum=65535))
        get = validate_answer(query, request(url + '?dns=' + encoded, maximum=65535))
        if get != post:
            raise ValueError('GET and POST returned different address sets')
        evidence[qtype] = post
    return evidence


if __name__ == '__main__':
    try:
        evidence = run(os.environ['DOH'], os.environ.get('VERIFY_NAME', 'unicast.uncensoreddns.org.'))
        for kind, ips in evidence.items():
            print(f'{kind}: HTTPS GET and POST passed; {len(ips)} address(es)')
    except Exception as exc:
        raise SystemExit('DoH acceptance FAILED: ' + type(exc).__name__ + ': ' + str(exc))
