"""Fixed SSH operation script; input is injected by controller.py, never shell text.

It preserves dirty/local-commit worktrees, receives no controller PAT, and emits
JSON only to an authenticated SSH pipe captured by the Actions controller.
"""
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

REPO_ROOT = Path('/workspaces/test1')
DNS_ROOT = REPO_ROOT / 'working/dns'
RUNTIME = DNS_ROOT / '.runtime'

class RemoteError(Exception):
    pass


def run(args, timeout=60):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0')
    p = subprocess.run(args, cwd=REPO_ROOT, env=env, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=timeout, text=True)
    if p.returncode:
        raise RemoteError('REMOTE_STEP_FAILED')
    return p.stdout.strip()


def atomic(path, data):
    temp = path.with_suffix('.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as out:
        json.dump(data, out)
    os.replace(temp, path)


def our_pid():
    try:
        value = (RUNTIME / 'pid').read_text().strip()
        if not value.isdigit():
            return None
        pid = int(value)
        cmd = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        scripts = {b'edge_server.py', b'managed_server.py'}
        if not any(Path(x.decode()).name.encode() in scripts for x in cmd if x):
            return None
        if Path(f'/proc/{pid}/cwd').resolve() != DNS_ROOT.resolve():
            return None
        return pid
    except (FileNotFoundError, ProcessLookupError, PermissionError, UnicodeError):
        return None


def stop_process():
    pid = our_pid()
    if pid:
        os.kill(pid, signal.SIGTERM)
        for _ in range(100):
            if our_pid() != pid:
                break
            time.sleep(.1)
        else:
            raise RemoteError('OLD_DNS_PROCESS_DID_NOT_STOP')
    # No unrelated process is killed for a recycled PID.
    (RUNTIME / 'pid').unlink(missing_ok=True)
    (RUNTIME / 'session.json').unlink(missing_ok=True)


def inspect():
    dirty = bool(run(['git', 'status', '--porcelain', '--untracked-files=all']))
    session = None
    legacy = False
    if our_pid() and (RUNTIME / 'session.json').is_file():
        value = json.loads((RUNTIME / 'session.json').read_text())
        if not value.get('managed_by_chat'):
            legacy = True
        elif value.get('expires_at_epoch', 0) > time.time() + 10:
            session = value
    lease = {}
    if (RUNTIME / 'managed-lease.json').is_file():
        lease = json.loads((RUNTIME / 'managed-lease.json').read_text())
    return {'ok': True, 'session': session, 'legacy_running': legacy, 'dirty': dirty,
            'lease_request_id': lease.get('request_id')}


def launch(config):
    commit = config.get('commit', '')
    expiry, rid = config.get('expires_at_epoch'), config.get('request_id')
    if not re.fullmatch(r'[a-f0-9]{40}', commit) or not re.fullmatch(r'[a-f0-9]{32}', str(rid)):
        raise RemoteError('INVALID_LAUNCH_IDENTIFIERS')
    if type(expiry) is not int or not time.time() + 30 < expiry <= time.time() + 10860:
        raise RemoteError('INVALID_LAUNCH_DEADLINE')
    if run(['git', 'status', '--porcelain', '--untracked-files=all']):
        raise RemoteError('WORKTREE_DIRTY_NOT_MODIFIED')
    git = ['git', '-c', 'core.hooksPath=/dev/null', '-c', 'protocol.file.allow=never']
    run(git + ['fetch', '--no-tags', 'https://github.com/efrgdgr0024345/test1.git', commit])
    # Fast-forward only: never reset, clean, force checkout, or delete local commits.
    try:
        run(git + ['merge', '--ff-only', '--no-edit', commit])
    except RemoteError:
        raise RemoteError('LOCAL_COMMITS_OR_DIVERGENCE_PRESERVED') from None
    if run(['git', 'rev-parse', 'HEAD']) != commit:
        raise RemoteError('STALE_COMMAND_WOULD_ROLL_BACK_CODE')
    stop_process()
    # Package installer output is private and never returned to public logs.
    run(['bash', 'working/dns/setup.sh'], timeout=180)
    lease = {'version': 2, 'request_id': rid, 'expires_at_epoch': expiry,
             'code_commit': commit, 'codespace': config['codespace']}
    atomic(RUNTIME / 'managed-lease.json', lease)
    # DNS process receives no GitHub credentials or unrelated Codespaces secrets.
    env = {k: os.environ[k] for k in ('PATH', 'HOME', 'LANG', 'LC_ALL') if k in os.environ}
    env['CODESPACE_NAME'] = config['codespace']
    env.setdefault('GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN', 'app.github.dev')
    with open(RUNTIME / 'managed.log', 'ab', buffering=0) as log:
        p = subprocess.Popen([str(DNS_ROOT / '.venv/bin/python'),
                  str(DNS_ROOT / 'control/managed_server.py')], cwd=DNS_ROOT,
                  stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                  start_new_session=True, close_fds=True, env=env)
    (RUNTIME / 'pid').write_text(str(p.pid))
    for _ in range(80):
        if p.poll() is not None:
            raise RemoteError('DNS_PROCESS_EXITED_DURING_STARTUP')
        if (RUNTIME / 'session.json').is_file():
            session = json.loads((RUNTIME / 'session.json').read_text())
            if session.get('request_id') == rid:
                return {'ok': True, 'session': session}
        time.sleep(.25)
    raise RemoteError('DNS_SESSION_FILE_TIMEOUT')


def main(config):
    os.umask(0o077)
    if not REPO_ROOT.is_dir() or run(['git', 'rev-parse', '--show-toplevel']) != str(REPO_ROOT):
        raise RemoteError('UNEXPECTED_WORKSPACE')
    origin = run(['git', 'remote', 'get-url', 'origin']).removesuffix('.git')
    if origin not in ('https://github.com/efrgdgr0024345/test1', 'git@github.com:efrgdgr0024345/test1'):
        raise RemoteError('WORKSPACE_REPOSITORY_MISMATCH')
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    operation = config.get('operation')
    if operation == 'inspect':
        return inspect()
    if operation == 'launch':
        return launch(config)
    if operation == 'accept':
        current = inspect().get('session')
        incoming = config.get('session', {})
        if not current or current['doh'] != incoming.get('doh') or current['request_id'] != incoming.get('request_id'):
            raise RemoteError('SESSION_CHANGED_DURING_ACCEPTANCE')
        if incoming.get('deployment_verified') is not True:
            raise RemoteError('ACCEPTANCE_RESULT_MISSING')
        current.update(deployment_verified=True, verification=incoming['verification'])
        atomic(RUNTIME / 'session.json', current)
        return {'ok': True, 'session': current}
    raise RemoteError('UNSUPPORTED_REMOTE_OPERATION')

if __name__ == '__main__':
    try:
        result = main(CONTROL_REQUEST)
    except RemoteError as exc:
        result = {'ok': False, 'error': str(exc)}
    except Exception:
        result = {'ok': False, 'error': 'REMOTE_OPERATION_FAILED'}
    print(json.dumps(result, separators=(',', ':')))
