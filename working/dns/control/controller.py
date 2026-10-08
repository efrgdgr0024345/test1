#!/usr/bin/env python3
"""Cloud-only Codespaces control. Secrets and usable URLs never enter public logs."""
from __future__ import annotations
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from protocol import ControlError, OWNER, REPO, TAG, select, seal, tagged_deadline, validate

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ControlError('API_REDIRECT_REJECTED')

class Cloud:
    def __init__(self, token: str):
        if not token:
            raise ControlError('MISSING_BLACKCAT_CODESPACES_PAT')
        self.token = token
        ctx = ssl.create_default_context()
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(), urllib.request.HTTPSHandler(context=ctx))

    def api(self, method: str, path: str, data=None):
        if not path.startswith(('/user/codespaces', '/repos/' + REPO + '/codespaces')):
            raise ControlError('API_PATH_REJECTED')
        req = urllib.request.Request('https://api.github.com' + path,
              data=None if data is None else json.dumps(data).encode(), method=method,
              headers={'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
                       'Content-Type': 'application/json', 'X-GitHub-Api-Version': '2026-03-10',
                       'User-Agent': 'BlackCatCloudControl/2'})
        try:
            with self.opener.open(req, timeout=25) as r:
                raw = r.read(1000001)
            if len(raw) > 1000000:
                raise ControlError('API_RESPONSE_TOO_LARGE')
            return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise ControlError('GITHUB_API_HTTP_' + str(exc.code)) from None
        except (urllib.error.URLError, TimeoutError):
            raise ControlError('GITHUB_API_UNREACHABLE') from None

    def owned(self):
        items = []
        for page in range(1, 11):
            data = self.api('GET', f'/repos/{REPO}/codespaces?per_page=100&page={page}')
            batch = data.get('codespaces', [])
            items.extend(batch)
            if len(batch) < 100:
                return items
        raise ControlError('CODESPACE_LIST_TRUNCATED')

    def get(self, name):
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,99}', name):
            raise ControlError('INVALID_CODESPACE_NAME')
        item = self.api('GET', '/user/codespaces/' + name)
        if item.get('repository', {}).get('full_name', '').lower() != REPO or item.get('owner', {}).get('login', '').lower() != OWNER:
            raise ControlError('CODESPACE_OWNERSHIP_MISMATCH')
        return item

    def wait(self, name, wanted, seconds=480):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            item = self.get(name)
            if item.get('state') in wanted:
                return item
            if item.get('state') in {'Failed', 'Deleted', 'Archived'}:
                raise ControlError('CODESPACE_NOT_RECOVERABLE')
            time.sleep(5)
        raise ControlError('CODESPACE_STATE_TIMEOUT')

    def stop(self, name):
        item = self.get(name)
        if item.get('state') != 'Shutdown':
            self.api('POST', '/user/codespaces/' + name + '/stop')
        self.wait(name, {'Shutdown'}, seconds=120)

    def gh(self, args, *, text=None, timeout=60):
        env = dict(os.environ)
        env.pop('BLACKCAT_CODESPACES_PAT', None)
        env.pop('GITHUB_TOKEN', None)
        env.update(GH_TOKEN=self.token, GH_PROMPT_DISABLED='1', GH_NO_UPDATE_NOTIFIER='1')
        try:
            r = subprocess.run(['gh', 'codespace', *args], input=text, text=True,
                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, env=env, check=False)
        except (subprocess.TimeoutExpired, OSError):
            raise ControlError('REMOTE_COMMAND_UNAVAILABLE') from None
        if r.returncode:
            # stderr can contain authentication URLs or capabilities. Never print it.
            raise ControlError('CODESPACE_SSH_OR_PORT_ACCESS_FAILED')
        if len(r.stdout) > 100000:
            raise ControlError('REMOTE_RESPONSE_TOO_LARGE')
        return r.stdout

    def remote(self, name, command, *, timeout=180):
        # SSH is authenticated through GitHub CLI. The PAT is NOT sent to the Codespace.
        script = 'CONTROL_REQUEST = ' + repr(command) + '\n' + (HERE / 'remote.py').read_text()
        raw = self.gh(['ssh', '-c', name, '--', '-T', 'python3', '-'], text=script, timeout=timeout)
        try:
            value = json.loads(raw)
        except ValueError:
            raise ControlError('REMOTE_RETURNED_NON_JSON') from None
        if not value.get('ok'):
            raise ControlError(value.get('error', 'REMOTE_OPERATION_FAILED'))
        return value

    def visibility(self, name, level):
        self.gh(['ports', 'visibility', '8080:' + level, '-c', name])


def check_session(session, name, *, now=None):
    now = time.time() if now is None else now
    origin = 'https://' + name + '-8080.app.github.dev'
    dashboard, doh = session.get('dashboard', ''), session.get('doh', '')
    u = urlsplit(dashboard)
    if u.scheme != 'https' or u.netloc != urlsplit(origin).netloc or u.query or u.fragment or not re.fullmatch(r'/s/[A-Za-z0-9_-]{32,128}/', u.path):
        raise ControlError('SESSION_URL_VALIDATION_FAILED')
    if doh != dashboard.rstrip('/') + '/working/dns' or session.get('public_origin') != origin:
        raise ControlError('SESSION_ENDPOINT_MISMATCH')
    expiry = session.get('expires_at_epoch')
    if type(expiry) is not int or not now + 10 < expiry <= now + 10860:
        raise ControlError('SESSION_EXPIRED_OR_INVALID_DEADLINE')
    if not re.fullmatch(r'[a-f0-9]{40}', str(session.get('code_commit', ''))):
        raise ControlError('SESSION_COMMIT_MISSING')
    return session


def acceptance(session, name):
    check_session(session, name)
    # Import the existing live verification suite without editing the resolver engine.
    sys.path.insert(0, str(ROOT))
    import verify
    with tempfile.TemporaryDirectory(prefix='blackcat-private-') as folder:
        path = Path(folder) / 'session.json'
        path.write_text(json.dumps(session)); path.chmod(0o600)
        old = verify.SESSION
        verify.SESSION = path
        try:
            # The existing verifier prints capability URLs. Capture them; NEVER relay its stdout.
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                verify.main()
            checked = json.loads(path.read_text())
        except Exception:
            raise ControlError('PUBLIC_HTTPS_ACCEPTANCE_FAILED') from None
        finally:
            verify.SESSION = old
    check_session(checked, name)
    return checked


def emit(command, payload):
    payload.update(request_id=command['request_id'], workflow_commit=os.environ.get('GITHUB_SHA'), checked_at_epoch=int(time.time()))
    envelope = seal(payload, command['reply_public_key'], command['request_id'])
    folder = Path(os.environ.get('RUNNER_TEMP', tempfile.gettempdir())) / 'blackcat-encrypted'
    folder.mkdir(mode=0o700, exist_ok=True)
    (folder / 'result.enc.json').write_text(json.dumps(envelope))
    print('BLACKCAT_ENCRYPTED_RESULT=' + base64.b64encode(json.dumps(envelope).encode()).decode(), flush=True)
    print('Black Cat result: ' + payload.get('state', 'UNKNOWN'), flush=True)


def reap(cloud):
    stopped = 0
    for item in cloud.owned():
        expiry = tagged_deadline(item)
        if expiry is not None and expiry <= time.time() and item.get('state') != 'Shutdown':
            cloud.stop(item['name'])
            stopped += 1
    print(f'Expiry sweep: {stopped} expired managed Codespace(s) confirmed stopped.')


def execute(cloud, command):
    operation = command['operation']
    item = select(cloud.owned(), command.get('codespace'))
    if item:
        item = cloud.get(item['name'])
    if operation == 'stop':
        if item:
            cloud.stop(item['name'])
        return {'state': 'STOPPED', 'codespace': item['name'] if item else None, 'live': False}
    if operation == 'status' and (not item or item.get('state') == 'Shutdown'):
        return {'state': 'STOPPED' if item else 'NOT_CREATED', 'live': False}
    changed = False
    name = item['name'] if item else None
    expiry = int(time.time()) + command['lifetime_seconds']
    try:
        if not item:
            machines = cloud.api('GET', '/repos/' + REPO + '/codespaces/machines').get('machines', [])
            small = [m for m in machines if 0 < m.get('cpus', 999) <= 2]
            if not small:
                raise ControlError('NO_TWO_CORE_MACHINE_AVAILABLE')
            machine = min(small, key=lambda m: (m['cpus'], m.get('memory_in_bytes', 0)))['name']
            # Tag expiry BEFORE creation; the independent reaper can recover failed startup.
            item = cloud.api('POST', '/repos/' + REPO + '/codespaces', {
                'ref': 'main', 'display_name': TAG + str(expiry), 'machine': machine,
                'devcontainer_path': '.devcontainer/devcontainer.json', 'idle_timeout_minutes': 180})
            name = item['name']; changed = True
        elif item.get('state') == 'Shutdown':
            if operation == 'status':
                return {'state': 'STOPPED', 'live': False}
            cloud.api('PATCH', '/user/codespaces/' + name, {'display_name': TAG + str(expiry)})
            changed = True
            cloud.api('POST', '/user/codespaces/' + name + '/start')
        cloud.wait(name, {'Available'})
        info = cloud.remote(name, {'operation': 'inspect'})
        existing = info.get('session')
        if existing and (operation != 'restart' or existing.get('request_id') == command['request_id']):
            # Repeated start/status never changes the existing lease or running code.
            checked = acceptance(existing, name)
            return {'state': 'LIVE', 'live': True, 'reused': True, 'codespace': name, 'session': checked}
        if operation == 'status':
            return {'state': 'LEGACY_RUNTIME' if info.get('legacy_running') else 'NOT_RUNNING', 'live': False, 'codespace': name}
        if info.get('lease_request_id') == command['request_id']:
            raise ControlError('REQUEST_ALREADY_CONSUMED_SESSION_ENDED')
        if info.get('dirty'):
            raise ControlError('WORKTREE_DIRTY_NOT_MODIFIED')
        if info.get('legacy_running') and operation != 'restart':
            raise ControlError('LEGACY_RUNTIME_NEEDS_RESTART')
        # Missing SSH on an old container fails above, without resetting or deleting its disk.
        cloud.api('PATCH', '/user/codespaces/' + name, {'display_name': TAG + str(expiry), 'idle_timeout_minutes': 180})
        changed = True
        info = cloud.remote(name, {'operation': 'launch', 'request_id': command['request_id'],
                                  'expires_at_epoch': expiry, 'commit': os.environ['GITHUB_SHA'],
                                  'codespace': name}, timeout=420)
        session = info['session']
        cloud.visibility(name, 'public')
        checked = None
        for delay in (2, 4, 8, 12):
            time.sleep(delay)
            try:
                checked = acceptance(session, name)
                break
            except ControlError:
                continue
        if checked is None:
            raise ControlError('PUBLIC_HTTPS_ACCEPTANCE_FAILED')
        current = cloud.remote(name, {'operation': 'accept', 'session': checked})
        if current['session']['doh'] != checked['doh']:
            raise ControlError('SESSION_CHANGED_DURING_ACCEPTANCE')
        return {'state': 'LIVE', 'live': True, 'reused': False, 'codespace': name, 'session': checked}
    except Exception:
        if changed and name:
            # Roll back machines this operation started/modified. Never delete user files.
            try:
                cloud.stop(name)
                print('Failed launch rolled back: machine confirmed stopped.')
            except Exception:
                print('STOP_NOT_CONFIRMED: inspect the Codespace; expiry sweep will retry.')
        raise


def main():
    os.umask(0o077)
    if os.environ.get('GITHUB_REPOSITORY', '').lower() != REPO or os.environ.get('GITHUB_REF') != 'refs/heads/main':
        raise ControlError('UNTRUSTED_WORKFLOW_CONTEXT')
    token = os.environ.get('BLACKCAT_CODESPACES_PAT', '')
    if len(sys.argv) > 1 and sys.argv[1] == '--reap':
        if not token:
            print('Expiry sweep is not configured: repository secret missing.')
            return
        return reap(Cloud(token))
    command = validate(json.loads((HERE / 'request.json').read_text()))
    try:
        payload = execute(Cloud(token), command)
    except Exception as exc:
        code = exc.code if isinstance(exc, ControlError) else 'UNEXPECTED_CONTROL_ERROR'
        emit(command, {'state': 'FAILED', 'live': False, 'error': code})
        raise ControlError(code) from None
    emit(command, payload)

if __name__ == '__main__':
    try:
        main()
    except ControlError as exc:
        print('Black Cat control failed: ' + exc.code, file=sys.stderr)
        sys.exit(1)
    except Exception:
        print('Black Cat control failed: UNEXPECTED_CONTROL_ERROR', file=sys.stderr)
        sys.exit(1)
