"""Absolute session deadlines survive process and machine restarts."""
import time


def remaining(lease: dict, now: float | None = None) -> int:
    now = time.time() if now is None else now
    value = lease.get('expires_at_epoch')
    if type(value) is not int or not now < value <= now + 10860:
        raise ValueError('Expired or invalid lease: a new chat request is required')
    return min(10800, int(value - now))
