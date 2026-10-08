#!/usr/bin/env python3
"""Time-limited wrapper around the existing DNS core. No controller PAT required."""
from __future__ import annotations
import datetime as dt
import json
import os
from pathlib import Path
import re
import signal
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from server import Engine, Provider, utc
from edge_server import LoopbackServer


from lease import remaining


def main():
    os.umask(0o077)
    runtime = ROOT / '.runtime'
    lease = json.loads((runtime / 'managed-lease.json').read_text())
    lifetime = remaining(lease)
    if lifetime < 10:
        raise ValueError('Session is too close to its fixed deadline')
    name = lease['codespace']
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,99}', name):
        raise ValueError('Invalid Codespace identifier')
    origin = 'https://' + name + '-8080.app.github.dev'
    providers = [Provider.load(x) for x in json.loads((ROOT / 'resolvers.json').read_text())]
    engine = Engine(providers, lifetime)
    server = LoopbackServer(('127.0.0.1', 8080), engine)
    endpoint = origin + engine.prefix
    session = {'dashboard': endpoint + '/', 'doh': endpoint + '/working/dns',
               'public_origin': origin, 'created_at': utc(), 'expires_after_seconds': lifetime,
               'expires_at_epoch': lease['expires_at_epoch'],
               'expires_at': dt.datetime.fromtimestamp(lease['expires_at_epoch'], dt.timezone.utc).isoformat(),
               'request_id': lease['request_id'], 'code_commit': lease['code_commit'],
               'managed_by_chat': True, 'deployment_verified': False,
               'security_model': 'Public HTTPS terminates at GitHub; application backend is loopback HTTP.'}
    target = runtime / 'session.json'
    temp = runtime / 'session.tmp'
    temp.write_text(json.dumps(session, indent=2)); temp.chmod(0o600)
    os.replace(temp, target)
    def stop(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    timer = threading.Timer(lifetime, stop); timer.daemon = True; timer.start()
    print('Managed DNS process started; session URLs remain in the private session file.', flush=True)
    try:
        server.serve_forever(poll_interval=.2)
    finally:
        timer.cancel(); server.server_close()
        if target.exists():
            try:
                if json.loads(target.read_text()).get('request_id') == lease['request_id']:
                    target.unlink()
            except (OSError, ValueError):
                pass
        engine.close()
        print('Managed DNS process stopped. Codespace compute cleanup is independent.', flush=True)

if __name__ == '__main__':
    main()
