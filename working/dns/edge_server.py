#!/usr/bin/env python3
"""GitHub Codespaces edge runtime.

The process binds HTTP ONLY to 127.0.0.1. GitHub's public forwarded-port edge is
the sole Internet listener and exposes the service as HTTPS. GitHub documents
that public forwarded ports use the normal forwarding mode; setting the
container-side protocol to HTTPS automatically changes a public port to private.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import signal
import threading
import time
from urllib.parse import urlsplit
import http.server

from server import Engine, Handler, Provider, utc

ROOT = Path(__file__).resolve().parent

class LoopbackServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    def __init__(self, address, engine):
        self.engine = engine
        self.proxy_https = False
        self.connections = threading.BoundedSemaphore(32)
        super().__init__(address, Handler)
    def process_request(self, request, client_address):
        if not self.connections.acquire(blocking=False):
            request.close()
            return
        super().process_request(request, client_address)
    def process_request_thread(self, request, client_address):
        try:
            request.settimeout(12)
            self.finish_request(request, client_address)
        except OSError:
            pass
        finally:
            self.shutdown_request(request)
            self.connections.release()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--public-origin", required=True)
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--lifetime", type=int, default=10800)
    args=p.parse_args()
    u=urlsplit(args.public_origin)
    if u.scheme != "https" or not u.hostname or u.path not in ("","/") or u.query or u.fragment:
        p.error("--public-origin must be one HTTPS origin")
    if not 60 <= args.lifetime <= 10800:
        p.error("--lifetime must be between 60 and 10800 seconds")
    providers=[Provider.load(x) for x in json.loads((ROOT/"resolvers.json").read_text())]
    engine=Engine(providers,args.lifetime)
    server=LoopbackServer(("127.0.0.1",args.port),engine)
    endpoint=args.public_origin.rstrip("/") + engine.prefix
    runtime=ROOT/".runtime"
    runtime.mkdir(mode=0o700,exist_ok=True)
    session={
        "dashboard":endpoint+"/",
        "doh":endpoint+"/working/dns",
        "public_origin":args.public_origin,
        "created_at":utc(),
        "expires_after_seconds":args.lifetime,
        "deployment_verified":False,
        "security_model":"Internet HTTPS terminates at GitHub Codespaces edge; container listener is loopback-only."
    }
    target=runtime/"session.json"
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,"w") as f: json.dump(session,f,indent=2)

    def stop(*_):
        threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)
    timer=threading.Timer(args.lifetime,stop); timer.daemon=True; timer.start()
    print("Loopback service ready at http://127.0.0.1:%d" % args.port,flush=True)
    print("Public URL is HTTPS only. See .runtime/session.json after the port is made public.",flush=True)
    try:
        server.serve_forever(poll_interval=.2)
    finally:
        timer.cancel(); server.server_close(); engine.close()
        target.unlink(missing_ok=True)

if __name__=="__main__": main()
