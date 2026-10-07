#!/usr/bin/env python3
"""Temporary, fail-closed, HTTPS-only multi-resolver DoH experiment.

Only dnspython parses DNS. All resolver connections use a pinned bootstrap IP
and verified TLS for the configured hostname. No UDP/TCP port 53, HTTP client,
redirect following, proxy-from-environment, or fabricated redirect IP exists.
"""
from __future__ import annotations
import argparse
import base64
import concurrent.futures
import copy
import dataclasses
import datetime as dt
import hashlib
import hmac
import http.client
import http.server
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import ssl
import threading
import time
from collections import OrderedDict
from urllib.parse import parse_qs, urlsplit

import dns.edns
import dns.exception
import dns.flags
import dns.message
import dns.name
import dns.opcode
import dns.rcode
import dns.rdatatype

ROOT = Path(__file__).resolve().parent
MAX_WIRE = 65535
SUPPORTED = {1, 2, 5, 6, 12, 15, 16, 28, 33, 35, 43, 48, 52, 64, 65, 257}
ADDRESS_TYPES = {1, 28, 64, 65}
DNSSEC_MATERIAL = {46, 47, 50, 51}


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def hostname(value: str) -> str:
    if not isinstance(value, str) or len(value) > 253:
        raise ValueError('Expected a public DNS hostname, not a URL or IP address')
    value = value.rstrip('.').encode('idna').decode('ascii').lower()
    labels = value.split('.')
    if len(labels) < 2 or any(not re.fullmatch(r'[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?', x) for x in labels):
        raise ValueError('Invalid public DNS hostname')
    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        raise ValueError('IP literals are not DNS hostnames')
    if value.endswith(('.local', '.localhost', '.internal', '.home.arpa')):
        raise ValueError('Private DNS names are not sent to public resolvers')
    return value + '.'


@dataclasses.dataclass(frozen=True)
class Provider:
    name: str
    url: str
    ip: str
    location: str

    @classmethod
    def load(cls, values: dict) -> 'Provider':
        p = cls(**values)
        u = urlsplit(p.url)
        if (u.scheme != 'https' or not u.hostname or u.port not in (None, 443)
                or u.username or u.password or u.query or u.fragment or not u.path):
            raise ValueError('Resolver URLs must be explicit HTTPS URLs on port 443')
        if not ipaddress.ip_address(p.ip).is_global:
            raise ValueError('Resolver bootstrap addresses must be public IPs')
        return p


class PinnedHTTPS(http.client.HTTPSConnection):
    """Use an IP for the socket, but the original hostname for TLS verification."""
    def __init__(self, host: str, ip: str, port: int, context: ssl.SSLContext):
        super().__init__(host, port=port, timeout=4, context=context)
        self.bootstrap_ip = str(ipaddress.ip_address(ip))

    def connect(self) -> None:
        sock = socket.create_connection((self.bootstrap_ip, self.port), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def fingerprint(msg: dns.message.Message) -> str:
    """Compare canonical RR data, never packet ordering, case, TTL, or RRSIG timing."""
    rows = set()
    for rrset in msg.answer:
        if rrset.rdtype in DNSSEC_MATERIAL:
            continue
        for rr in rrset:
            rows.add((rrset.name.canonicalize().to_wire().hex(), rrset.rdclass,
                      rrset.rdtype, rr.to_digestable().hex()))
    return json.dumps([msg.rcode(), sorted(rows)], separators=(',', ':'))


def describe(msg: dns.message.Message) -> dict:
    records, ips, ttls = [], set(), []
    for rrset in msg.answer:
        if rrset.rdtype in DNSSEC_MATERIAL:
            continue
        ttls.append(rrset.ttl)
        for rr in rrset:
            records.append({'owner': rrset.name.to_text(),
                            'type': dns.rdatatype.to_text(rrset.rdtype),
                            'value': rr.to_text(), 'ttl': rrset.ttl})
            if rrset.rdtype in (1, 28):
                ips.add(str(ipaddress.ip_address(rr.address)))
    # Negative cache lifetime is also bounded by the SOA minimum.
    for rrset in msg.authority:
        if rrset.rdtype == dns.rdatatype.SOA:
            ttls.extend(min(rrset.ttl, rr.minimum) for rr in rrset)
    return {'rcode': dns.rcode.to_text(msg.rcode()), 'ips': sorted(ips),
            'records': records, 'ad_reported': bool(msg.flags & dns.flags.AD),
            'ttl': min(ttls, default=0)}


def ask(p: Provider, name: str, qtype: int, context: ssl.SSLContext | None = None) -> dict:
    started = time.monotonic()
    result = {'provider': p.name, 'endpoint': p.url, 'bootstrap_ip': p.ip,
              'location': p.location, 'location_basis': 'operator published; not measured',
              'qtype': dns.rdatatype.to_text(qtype), 'checked_at': utc()}
    conn = None
    try:
        query = dns.message.make_query(name, qtype, use_edns=0, want_dnssec=True)
        query.flags |= dns.flags.AD
        query.flags &= ~dns.flags.CD
        u = urlsplit(p.url)
        context = context or ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        conn = PinnedHTTPS(u.hostname, p.ip, u.port or 443, context)
        conn.request('POST', u.path, body=query.to_wire(), headers={
            'Accept': 'application/dns-message', 'Content-Type': 'application/dns-message',
            'User-Agent': 'BlackCat-ConsensusDoH/0.1', 'Connection': 'close'})
        response = conn.getresponse()
        if response.status != 200:
            raise ValueError(f'Upstream HTTP status {response.status}; redirects are not followed')
        if response.getheader('Content-Type', '').split(';')[0].strip().lower() != 'application/dns-message':
            raise ValueError('Upstream did not return a DNS message')
        wire = response.read(MAX_WIRE + 1)
        if len(wire) > MAX_WIRE:
            raise ValueError('Oversized upstream DNS response')
        msg = dns.message.from_wire(wire, ignore_trailing=False)
        if not query.is_response(msg) or msg.flags & dns.flags.TC:
            raise ValueError('Mismatched or truncated upstream response')
        if msg.rcode() not in (dns.rcode.NOERROR, dns.rcode.NXDOMAIN):
            raise ValueError('Upstream DNS error: ' + dns.rcode.to_text(msg.rcode()))
        result.update(describe(msg), error=None, _message=msg, _fingerprint=fingerprint(msg))
    except Exception as exc:
        result.update(error=f'{type(exc).__name__}: {str(exc)[:200]}', ips=[], records=[],
                      rcode=None, ad_reported=False, ttl=0)
    finally:
        if conn:
            conn.close()
        result['milliseconds'] = round((time.monotonic() - started) * 1000, 1)
    return result


def verdict(rows: list[dict]) -> str:
    identities = {r['_fingerprint'] for r in rows if not r.get('error')}
    if len(identities) > 1:
        return 'mismatch'
    if any(r.get('error') for r in rows) or len(rows) < 3:
        return 'unavailable'
    return 'match'


class Engine:
    def __init__(self, providers: list[Provider], lifetime: int = 10800, query=ask):
        if not 3 <= len(providers) <= 8:
            raise ValueError('Configure three to eight independently operated resolvers')
        self.providers, self.query = providers, query
        self.started, self.expires = time.monotonic(), time.monotonic() + lifetime
        self.token = secrets.token_urlsafe(32)
        self.prefix = '/s/' + self.token
        self.lock = threading.Lock()
        self.cache: OrderedDict = OrderedDict()
        self.reports: OrderedDict = OrderedDict()
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=24)
        self.slots = threading.BoundedSemaphore(8)
        self.budget, self.last_budget = 6.0, time.monotonic()

    def expired(self) -> bool:
        return time.monotonic() >= self.expires

    def compare(self, name: str, qtype: int) -> dict:
        if self.expired():
            raise RuntimeError('This temporary session has expired')
        key, now = (name, qtype), time.monotonic()
        with self.lock:
            cached = self.cache.get(key)
            if cached and cached[0] > now:
                result = copy.deepcopy(cached[1])
                result['cache_age_seconds'] = round(now - cached[2], 2)
                return result
            # Per-service budget, not an IP limit that a caller could spoof.
            self.budget = min(6.0, self.budget + (now - self.last_budget) * 3.0)
            self.last_budget = now
            if self.budget < 1:
                raise RuntimeError('Query budget exceeded; retry shortly')
            self.budget -= 1
        if not self.slots.acquire(blocking=False):
            raise RuntimeError('Resolver concurrency limit reached')
        try:
            futures = [self.pool.submit(self.query, p, name, qtype) for p in self.providers]
            rows = [f.result(timeout=6) for f in futures]
            if self.expired():
                raise RuntimeError('This temporary session has expired')
            result = {'name': name, 'qtype': dns.rdatatype.to_text(qtype),
                      'status': verdict(rows), 'rows': rows, 'checked_at': utc(),
                      'cache_age_seconds': 0}
            # Five seconds at most, never beyond the lowest received TTL.
            ttl = min(5, *(r['ttl'] for r in rows)) if result['status'] == 'match' else 0
            with self.lock:
                if ttl > 0:
                    self.cache[key] = (time.monotonic() + ttl, copy.deepcopy(result), time.monotonic())
                    while len(self.cache) > 512:
                        self.cache.popitem(last=False)
            return result
        finally:
            self.slots.release()

    def gate(self, name: str, extra: int | None = None) -> dict:
        if self.expired():
            raise RuntimeError('This temporary session has expired')
        types = [1, 28]
        if extra not in (None, 1, 28):
            types.append(extra)
        comparisons = [self.compare(name, q) for q in types]
        states = [c['status'] for c in comparisons]
        status = 'mismatch' if 'mismatch' in states else ('unavailable' if 'unavailable' in states else 'match')
        existence = {r['rcode'] for c in comparisons[:2] for r in c['rows'] if not r.get('error')}
        if status == 'match' and len(existence) > 1:
            status = 'mismatch'  # A and AAAA cannot agree on contradictory name existence.
        addresses = sorted({ip for c in comparisons[:2] for row in c['rows'] for ip in row['ips']})
        report = {'id': secrets.token_urlsafe(18), 'name': name, 'status': status,
                  'allowed': status == 'match' and bool(addresses), 'ips': addresses,
                  'checked_at': utc(), 'comparisons': comparisons,
                  'policy': 'unanimous IPv4 AND IPv6; every configured resolver must answer',
                  'note': 'Agreement is not proof of authenticity. Location labels are not measured probe locations.'}
        self.save(report)
        return report

    def save(self, report: dict) -> None:
        # Drop DNS objects from stored reports. Nothing is written to disk.
        clean = public(report)
        with self.lock:
            self.reports[report['id']] = (time.monotonic() + 600, clean)
            for key in list(self.reports):
                if self.reports[key][0] < time.monotonic():
                    del self.reports[key]
            while len(self.reports) > 256:
                self.reports.popitem(last=False)

    def get_report(self, rid: str) -> dict | None:
        with self.lock:
            stored = self.reports.get(rid)
            return copy.deepcopy(stored[1]) if stored and stored[0] > time.monotonic() else None

    def dns_answer(self, query: dns.message.Message) -> dns.message.Message:
        name = hostname(query.question[0].name.to_text())
        qtype = query.question[0].rdtype
        if qtype not in SUPPORTED:
            return blocked(query, 'Unsupported query type', 21)
        if qtype in ADDRESS_TYPES:
            report = self.gate(name, qtype)
            comparison = next(c for c in report['comparisons'] if c['qtype'] == dns.rdatatype.to_text(qtype))
            status = report['status']
        else:
            comparison = self.compare(name, qtype)
            status = comparison['status']
            report = {'id': secrets.token_urlsafe(18), 'name': name, 'status': status,
                      'allowed': status == 'match', 'checked_at': utc(),
                      'comparisons': [comparison]}
            self.save(report)
        if status != 'match':
            return blocked(query, f'{status}; report {report["id"]}', 15)
        answer = copy.deepcopy(comparison['rows'][0]['_message'])
        answer.id = query.id
        answer.question = copy.deepcopy(query.question)
        answer.flags &= ~(dns.flags.AA | dns.flags.CD | dns.flags.AD)
        answer.flags |= dns.flags.RA
        if all(row['ad_reported'] for row in comparison['rows']):
            answer.flags |= dns.flags.AD
        if not query.flags & dns.flags.RD:
            answer.flags &= ~dns.flags.RD
        # No un-compared additional IP/glue can bypass address checks.
        answer.additional = []
        age = comparison.get('cache_age_seconds', 0)
        ttl_cap = min(5, *(row['ttl'] for row in comparison['rows']))
        for rrset in answer.answer + answer.authority:
            rrset.ttl = max(0, min(int(ttl_cap - age), int(rrset.ttl - age)))
        if not query.ednsflags & dns.flags.DO:
            answer.answer = [x for x in answer.answer if x.rdtype not in DNSSEC_MATERIAL or x.rdtype == qtype]
            answer.authority = [x for x in answer.authority if x.rdtype not in DNSSEC_MATERIAL]
        # Do not relay upstream EDNS cookies, client-subnet data, or opaque options.
        answer.use_edns(edns=0 if query.edns >= 0 else False,
                        ednsflags=(dns.flags.DO if query.ednsflags & dns.flags.DO else 0),
                        payload=1232, options=[])
        return answer

    def close(self) -> None:
        self.pool.shutdown(wait=True, cancel_futures=True)
        with self.lock:
            self.cache.clear()
            self.reports.clear()


def public(value):
    if isinstance(value, dict):
        return {k: public(v) for k, v in value.items() if not k.startswith('_')}
    if isinstance(value, list):
        return [public(v) for v in value]
    return value


def blocked(query: dns.message.Message, reason: str, code: int = 15) -> dns.message.Message:
    answer = dns.message.make_response(query)
    answer.set_rcode(dns.rcode.SERVFAIL)
    answer.flags |= dns.flags.RA
    answer.flags &= ~(dns.flags.AD | dns.flags.CD)
    if query.edns >= 0:
        answer.use_edns(options=[dns.edns.EDEOption(code, reason[:180])])
    return answer


def parse_query(wire: bytes) -> dns.message.Message:
    if not 12 <= len(wire) <= 4096:
        raise ValueError('DNS query length must be 12..4096 bytes')
    q = dns.message.from_wire(wire, ignore_trailing=False)
    if (q.flags & dns.flags.QR or q.opcode() != dns.opcode.QUERY or len(q.question) != 1
            or q.question[0].rdclass != 1 or q.answer or q.authority or q.additional
            or q.had_tsig or q.edns > 0):
        raise ValueError('Only one-question standard IN-class DNS queries are supported')
    return q


class TLSServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, engine: Engine, context: ssl.SSLContext, proxy_https=False):
        self.engine, self.tls_context, self.proxy_https = engine, context, proxy_https
        self.connections = threading.BoundedSemaphore(32)
        super().__init__(address, Handler)

    def process_request(self, request, client_address):
        if not self.connections.acquire(blocking=False):
            request.close()
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address):
        secured = None
        try:
            request.settimeout(12)
            secured = self.tls_context.wrap_socket(request, server_side=True)
            self.finish_request(secured, client_address)
        except (OSError, ssl.SSLError):
            pass
        finally:
            self.shutdown_request(secured or request)
            self.connections.release()


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'BlackCatDoH/0.1'
    sys_version = ''

    def log_message(self, fmt, *args):
        pass  # Capability paths, domains, and client addresses are never access-logged.

    def send(self, code, content: bytes, kind='application/json'):
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Strict-Transport-Security', 'max-age=31536000')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True
        if self.command != 'HEAD':
            self.wfile.write(content)

    def data(self, code, obj):
        self.send(code, json.dumps(public(obj)).encode())

    def body(self, maximum=4096) -> bytes:
        if self.headers.get('Transfer-Encoding'):
            raise ValueError('Chunked request bodies are not accepted')
        lengths = self.headers.get_all('Content-Length', [])
        if len(lengths) != 1 or not lengths[0].isdigit():
            raise ValueError('Exactly one valid Content-Length is required')
        size = int(lengths[0])
        if not 0 <= size <= maximum:
            raise ValueError('Request body is too large')
        body = self.rfile.read(size)
        if len(body) != size:
            raise ValueError('Incomplete request body')
        return body

    def do_GET(self):
        self.route()

    def do_POST(self):
        self.route()

    def route(self):
        e = self.server.engine
        try:
            if len(self.path) > 8192:
                return self.data(414, {'error': 'Request target too long'})
            # On Codespaces, require the edge to attest the ORIGINAL request was HTTPS.
            # Deployment acceptance tests must verify GitHub overwrites spoofed headers.
            forwarded = self.headers.get_all('X-Forwarded-Proto', [])
            if self.server.proxy_https and forwarded != ['https']:
                return self.data(403, {'error': 'Original transport must be HTTPS'})
            if e.expired():
                return self.data(410, {'error': 'Session expired'})
            u = urlsplit(self.path)
            if self.command == 'GET' and u.path == '/healthz':
                return self.data(200, {'service': 'black-cat-doh', 'transport': 'TLS-only',
                                       'state': 'process-ready; upstream checks are separate'})
            pieces = u.path.split('/')
            if len(pieces) < 4 or pieces[1] != 's' or not hmac.compare_digest(pieces[2], e.token):
                return self.data(404, {'error': 'Not found'})
            path = '/' + '/'.join(pieces[3:])
            if path == '/working/dns':
                if self.command == 'POST':
                    if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/dns-message':
                        return self.data(415, {'error': 'Use application/dns-message'})
                    wire = self.body()
                else:
                    args = parse_qs(u.query, keep_blank_values=True)
                    if set(args) != {'dns'} or len(args['dns']) != 1:
                        raise ValueError('Expected exactly one dns parameter')
                    encoded = args['dns'][0]
                    if not re.fullmatch(r'[A-Za-z0-9_-]+', encoded):
                        raise ValueError('Use unpadded base64url')
                    wire = base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4))
                query = parse_query(wire)
                try:
                    answer = e.dns_answer(query)
                except (RuntimeError, ValueError) as exc:
                    answer = blocked(query, str(exc), 14)
                return self.send(200, answer.to_wire(max_size=MAX_WIRE), 'application/dns-message')
            if path == '/api/check' and self.command == 'POST':
                if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
                    return self.data(415, {'error': 'Use application/json'})
                data = json.loads(self.body(1024))
                name = hostname(data.get('name', ''))
                return self.data(200, e.gate(name))
            if path.startswith('/api/reports/') and self.command == 'GET':
                report = e.get_report(path.rsplit('/', 1)[-1])
                return self.data(200 if report else 404, report or {'error': 'Report expired or unknown'})
            if self.command == 'GET' and (path == '/' or path.startswith('/reports/')):
                html = (ROOT / 'web/index.html').read_text().replace('@@PREFIX@@', e.prefix)
                return self.send(200, html.encode(), 'text/html; charset=utf-8')
            if self.command == 'GET' and path in ('/app.js', '/style.css'):
                kind = 'text/javascript' if path.endswith('.js') else 'text/css'
                return self.send(200, (ROOT / 'web' / path[1:]).read_bytes(), kind + '; charset=utf-8')
            return self.data(404, {'error': 'Not found'})
        except (ValueError, KeyError, TypeError, dns.exception.DNSException) as exc:
            self.data(400, {'error': str(exc)[:180]})
        except (RuntimeError, concurrent.futures.TimeoutError) as exc:
            self.data(503, {'error': str(exc)[:180]})
        except Exception:
            self.data(500, {'error': 'Internal error; request failed closed'})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cert', required=True)
    p.add_argument('--key', required=True)
    p.add_argument('--public-origin', required=True)
    p.add_argument('--port', type=int, default=8443)
    p.add_argument('--lifetime', type=int, default=10800)
    p.add_argument('--require-proxy-https', action='store_true')
    args = p.parse_args()
    u = urlsplit(args.public_origin)
    if u.scheme != 'https' or not u.hostname or u.path not in ('', '/') or u.query or u.fragment or u.username:
        p.error('--public-origin must be an HTTPS origin')
    if not 60 <= args.lifetime <= 10800:
        p.error('--lifetime must be between 60 and 10800 seconds')
    providers = [Provider.load(row) for row in json.loads((ROOT / 'resolvers.json').read_text())]
    if len({urlsplit(x.url).hostname for x in providers}) != len(providers):
        p.error('Do not count the same resolver host as multiple independent providers')
    engine = Engine(providers, args.lifetime)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(args.cert, args.key)
    server = TLSServer(('0.0.0.0', args.port), engine, context, args.require_proxy_https)
    endpoint = args.public_origin.rstrip('/') + engine.prefix
    session = {'dashboard': endpoint + '/', 'doh': endpoint + '/working/dns',
               'expires_after_seconds': args.lifetime, 'created_at': utc(),
               'deployment_verified': False}
    runtime = ROOT / '.runtime'
    runtime.mkdir(mode=0o700, exist_ok=True)
    target = runtime / 'session.json'
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as out:
        json.dump(session, out, indent=2)
    def stop(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    timer = threading.Timer(args.lifetime, stop)
    timer.daemon = True
    timer.start()
    print('TLS service started. Private session addresses are in .runtime/session.json.', flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        timer.cancel()
        server.server_close()
        engine.close()
        target.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
