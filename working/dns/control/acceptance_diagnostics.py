#!/usr/bin/env python3
"""Run unchanged live HTTPS acceptance, retaining redacted failures in encrypted replies."""
from __future__ import annotations
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import controller
import diagnose
from protocol import ControlError


def acceptance(session, name):
    controller.check_session(session, name)
    from edge_probe import probe
    probe(session)
    sys.path.insert(0, str(controller.ROOT))
    import verify
    captured = io.StringIO()
    with tempfile.TemporaryDirectory(prefix='blackcat-private-') as folder:
        path = Path(folder) / 'session.json'
        path.write_text(json.dumps(session)); path.chmod(0o600)
        old = verify.SESSION
        verify.SESSION = path
        try:
            with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
                verify.main()
            checked = json.loads(path.read_text())
        except Exception as exc:
            diagnose.note('acceptance_failure', error_type=type(exc).__name__,
                          reason=diagnose.redact(str(exc)),
                          stage=diagnose.redact(captured.getvalue()))
            raise ControlError('PUBLIC_HTTPS_ACCEPTANCE_FAILED') from None
        finally:
            verify.SESSION = old
    controller.check_session(checked, name)
    diagnose.note('acceptance_success', coverage='public HTTPS dashboard, HTTP refusal/upgrade, unanimous A and AAAA, DoH GET and POST')
    return checked


def main():
    controller.acceptance = acceptance
    diagnose.main()


if __name__ == '__main__':
    try:
        main()
    except ControlError as exc:
        print('Black Cat control failed: ' + exc.code, file=sys.stderr)
        sys.exit(1)
    except Exception:
        print('Black Cat control failed: UNEXPECTED_CONTROL_ERROR', file=sys.stderr)
        sys.exit(1)
