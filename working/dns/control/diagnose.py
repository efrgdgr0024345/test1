#!/usr/bin/env python3
"""Run the existing controller with bounded, redacted, encrypted diagnostics.

Only public phase names are logged. No token or usable session address appears
in diagnostics; the existing encrypted result carries diagnostic details.
"""
from __future__ import annotations
import os
import re
import subprocess
import sys
import time
import controller
from protocol import ControlError

DIAGNOSTICS = []

def redact(value, token=''):
    text = value.decode(errors='replace') if isinstance(value, bytes) else str(value or '')
    if token:
        text = text.replace(token, '[credential removed]')
    text = re.sub(r'(?im)(authorization\s*[:=]\s*)[^\r\n]+', r'\1[removed]', text)
    text = re.sub(r'(?i)\b(?:github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9_]+)\b', '[credential removed]', text)
    text = re.sub(r'https?://[^\s<>"\']+', '[URL removed]', text)
    text = re.sub(r'/s/[A-Za-z0-9_-]{20,}', '/s/[capability removed]', text)
    return text[-6000:]


def note(kind, **fields):
    DIAGNOSTICS.append({'kind': kind, **fields})
    if len(DIAGNOSTICS) > 30:
        del DIAGNOSTICS[0]


class DiagnosticCloud(controller.Cloud):
    def api(self, method, path, data=None):
        # Codespace names are private diagnostics; no credentials are in path.
        started = time.monotonic()
        try:
            result = super().api(method, path, data)
        except ControlError as exc:
            note('api_failure', method=method, path=redact(path, self.token), code=exc.code)
            raise
        if method != 'GET' or '/machines' in path or '?per_page' in path:
            print('CLOUD_PHASE: GitHub ' + method + ' request completed.', flush=True)
        if isinstance(result, dict) and result.get('name') and result.get('state'):
            note('codespace', name=result['name'], state=result['state'],
                 created_at=result.get('created_at'), updated_at=result.get('updated_at'),
                 machine=(result.get('machine') or {}).get('name'),
                 git_status=result.get('git_status'),
                 elapsed_seconds=round(time.monotonic()-started, 2))
        return result

    def gh(self, args, *, text=None, timeout=60):
        env = dict(os.environ)
        for key in ('BLACKCAT_CODESPACES_PAT', 'GITHUB_TOKEN', 'GH_DEBUG', 'GIT_TRACE', 'GIT_CURL_VERBOSE'):
            env.pop(key, None)
        env.update(GH_TOKEN=self.token, GH_PROMPT_DISABLED='1', GH_NO_UPDATE_NOTIFIER='1')
        step = args[0] if args else 'unknown'
        print('CLOUD_PHASE: GitHub CLI ' + step + '.', flush=True)
        started = time.monotonic()
        try:
            r = subprocess.run(['gh', 'codespace', *args], input=text, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=timeout, env=env, check=False)
        except subprocess.TimeoutExpired as exc:
            note('cli_timeout', operation=step, seconds=timeout,
                 stderr=redact(exc.stderr, self.token))
            raise ControlError('CODESPACE_CLI_TIMEOUT') from None
        except OSError as exc:
            note('cli_unavailable', operation=step, error=redact(str(exc), self.token))
            raise ControlError('CODESPACE_CLI_UNAVAILABLE') from None
        if r.returncode:
            note('cli_failure', operation=step, returncode=r.returncode,
                 elapsed_seconds=round(time.monotonic()-started, 2),
                 stderr=redact(r.stderr, self.token), stdout=redact(r.stdout, self.token))
            raise ControlError('CODESPACE_' + ('SSH' if step == 'ssh' else 'PORT') + '_FAILED')
        if len(r.stdout) > 100000:
            raise ControlError('REMOTE_RESPONSE_TOO_LARGE')
        note('cli_success', operation=step, elapsed_seconds=round(time.monotonic()-started, 2))
        return r.stdout


def main():
    try:
        version = subprocess.run(['gh', '--version'], text=True, capture_output=True, timeout=10)
        note('cli_version', version=redact(version.stdout.splitlines()[0] if version.stdout else 'unknown'))
    except (OSError, subprocess.TimeoutExpired):
        note('cli_version', version='unavailable')
    original_emit = controller.emit
    def diagnostic_emit(command, payload):
        payload['diagnostics'] = DIAGNOSTICS[-30:]
        return original_emit(command, payload)
    controller.Cloud = DiagnosticCloud
    controller.emit = diagnostic_emit
    controller.main()


if __name__ == '__main__':
    try:
        main()
    except ControlError as exc:
        print('Black Cat control failed: ' + exc.code, file=sys.stderr)
        sys.exit(1)
    except Exception:
        print('Black Cat control failed: UNEXPECTED_CONTROL_ERROR', file=sys.stderr)
        sys.exit(1)
