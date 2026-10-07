"""Pinned-IP, hostname-verified HTTP/2 transport for the existing resolver engine.

Uses HTTPX's documented sni_hostname extension. The URL contains the bootstrap
IP, while Host and TLS SNI/certificate validation use the resolver hostname.
"""
from __future__ import annotations
import ipaddress
import ssl
import time
import httpx

class PinnedHTTPS:
    def __init__(self, host: str, ip: str, port: int, context: ssl.SSLContext):
        address = ipaddress.ip_address(ip)
        if port != 443 or not address.is_global:
            raise ValueError('Only public bootstrap IPs on HTTPS port 443 are permitted')
        if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
            raise ValueError('Verified TLS and hostname validation are mandatory')
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.host = host
        self.address = '[' + str(address) + ']' if address.version == 6 else str(address)
        self.client = httpx.Client(http1=False, http2=True, verify=context,
                                  trust_env=False, follow_redirects=False, timeout=4.0)
        self.response = None
        self.deadline = None

    def request(self, method: str, path: str, body: bytes, headers: dict) -> None:
        if method != 'POST' or not path.startswith('/') or path.startswith('//'):
            raise ValueError('Only a relative DoH POST path is supported')
        clean = {k: v for k, v in headers.items()
                 if k.lower() not in ('connection', 'host', 'accept-encoding')}
        clean['Host'] = self.host
        clean['Accept-Encoding'] = 'identity'
        req = self.client.build_request('POST', 'https://' + self.address + path,
                                        content=body, headers=clean,
                                        extensions={'sni_hostname': self.host})
        self.deadline = time.monotonic() + 4.0
        self.response = self.client.send(req, stream=True, follow_redirects=False)
        if self.response.http_version != 'HTTP/2':
            raise ValueError('The configured upstream must support HTTP/2 over TLS')

    def getresponse(self):
        if self.response is None:
            raise ValueError('No upstream response')
        return self

    @property
    def status(self) -> int:
        return self.response.status_code

    def getheader(self, key: str, default=None):
        return self.response.headers.get(key, default)

    def read(self, maximum: int) -> bytes:
        if self.response.headers.get('content-encoding', 'identity') != 'identity':
            raise ValueError('Compressed upstream DNS responses are not accepted')
        data = bytearray()
        for chunk in self.response.iter_bytes():
            if time.monotonic() > self.deadline:
                raise TimeoutError('Upstream response exceeded the total read deadline')
            remaining = maximum - len(data)
            data.extend(chunk[:remaining])
            if len(data) >= maximum:
                break
        return bytes(data)

    def close(self) -> None:
        try:
            if self.response is not None:
                self.response.close()
        finally:
            self.client.close()
