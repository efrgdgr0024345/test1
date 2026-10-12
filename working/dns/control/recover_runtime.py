#!/usr/bin/env python3
"""One-time non-destructive migration of the confirmed pre-SSH Codespace.

The original machine is never rebuilt or deleted. A replacement is created
only when this repository has no other candidate; existing replacements are
reused. The standard controller still enforces the DNS policy and acceptance.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import time
import controller
from diagnose import DIAGNOSTICS, DiagnosticCloud, note
from protocol import ControlError, REPO, TAG, select, validate

LEGACY = 'legendary-pancake-r49q5wxpwppr3pwrv'
PRESERVED = 'BlackCatDNS-preserved-no-sshd'


def candidates(items):
    return [x for x in items if x.get('name') != LEGACY]


def require_stopped_legacy(item):
    if item.get('name') != LEGACY or item.get('repository', {}).get('full_name', '').lower() != REPO:
        raise ControlError('RECOVERY_LEGACY_IDENTITY_MISMATCH')
    if item.get('state') != 'Shutdown':
        raise ControlError('RECOVERY_LEGACY_MUST_REMAIN_STOPPED')


def small_machine(machines):
    allowed = [m for m in machines if type(m.get('cpus')) is int and 0 < m['cpus'] <= 2]
    if not allowed:
        raise ControlError('NO_TWO_CORE_MACHINE_AVAILABLE')
    return min(allowed, key=lambda m: (m['cpus'], m.get('memory_in_bytes', 0)))['name']


def main():
    os.umask(0o077)
    if os.environ.get('GITHUB_REPOSITORY', '').lower() != REPO or os.environ.get('GITHUB_REF') != 'refs/heads/main':
        raise ControlError('UNTRUSTED_WORKFLOW_CONTEXT')
    command = validate(json.loads((Path(__file__).parent / 'request.json').read_text()))
    if command['operation'] != 'start':
        raise ControlError('RECOVERY_ONLY_ACCEPTS_START')
    cloud = None
    created = None
    try:
        cloud = DiagnosticCloud(os.environ.get('BLACKCAT_CODESPACES_PAT', ''))
        legacy = cloud.get(LEGACY)
        require_stopped_legacy(legacy)
        other = select(candidates(cloud.owned()), command.get('codespace'))
        if other is None:
            # The authenticated existing-Codespace response includes its machine
            # name AND CPU count. Reuse that verified small tier; no machine
            # catalog permission or unverified/larger default is needed.
            existing_machine = legacy.get('machine') or {}
            machine = small_machine([existing_machine])
            note('selected_machine', name=machine, cpus=existing_machine['cpus'])
            deadline = int(time.time()) + command['lifetime_seconds']
            other = cloud.api('POST', '/repos/' + REPO + '/codespaces', {
                'ref': 'main', 'display_name': TAG + str(deadline), 'machine': machine,
                'devcontainer_path': '.devcontainer/devcontainer.json', 'idle_timeout_minutes': 180})
            created = other['name']
            note('replacement_created', codespace=created, preserved_codespace=LEGACY)
        # Only the display label changes; no original disk or source file changes.
        if str(legacy.get('display_name', '')).startswith(TAG):
            cloud.api('PATCH', '/user/codespaces/' + LEGACY, {'display_name': PRESERVED})
        selected_command = dict(command, codespace=other['name'])
        payload = controller.execute(cloud, selected_command)
        payload['preserved_codespaces'] = [LEGACY]
    except Exception as exc:
        if created and cloud is not None:
            try:
                cloud.stop(created)
                print('Replacement launch failed; replacement machine confirmed stopped.', flush=True)
            except Exception:
                print('STOP_NOT_CONFIRMED: replacement remains subject to expiry cleanup.', flush=True)
        code = exc.code if isinstance(exc, ControlError) else 'UNEXPECTED_RECOVERY_ERROR'
        payload = {'state': 'FAILED', 'live': False, 'error': code,
                   'preserved_codespaces': [LEGACY], 'replacement_codespace': created}
        payload['diagnostics'] = DIAGNOSTICS[-30:]
        controller.emit(command, payload)
        raise ControlError(code) from None
    payload['diagnostics'] = DIAGNOSTICS[-30:]
    controller.emit(command, payload)


if __name__ == '__main__':
    try:
        main()
    except ControlError as exc:
        print('Black Cat control failed: ' + exc.code, file=sys.stderr)
        sys.exit(1)
    except Exception:
        print('Black Cat control failed: UNEXPECTED_RECOVERY_ERROR', file=sys.stderr)
        sys.exit(1)
