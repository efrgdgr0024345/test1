"""Validated commands and encrypted replies. Never stores a private reply key."""
from __future__ import annotations
import base64
import json
import os
import re
import time
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

REPO = 'efrgdgr0024345/test1'
OWNER = REPO.split('/')[0]
TAG = 'BlackCatDNS-v2-'
OPS = {'start', 'status', 'stop', 'restart'}

class ControlError(Exception):
    """Only static error codes may be written to public logs."""
    def __init__(self, code: str):
        if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,95}', code):
            code = 'INTERNAL_ERROR'
        self.code = code
        super().__init__(code)


def public_key(pem: str):
    if not isinstance(pem, str) or len(pem) > 8192:
        raise ControlError('INVALID_REPLY_PUBLIC_KEY')
    try:
        key = serialization.load_pem_public_key(pem.encode('ascii'))
    except (ValueError, TypeError, UnicodeError):
        raise ControlError('INVALID_REPLY_PUBLIC_KEY') from None
    if not isinstance(key, rsa.RSAPublicKey) or not 3072 <= key.key_size <= 4096:
        raise ControlError('REPLY_KEY_MUST_BE_RSA_3072_OR_4096')
    return key


def validate(command: dict, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    keys = {'version', 'operation', 'request_id', 'lifetime_seconds',
            'reply_public_key', 'codespace', 'issued_at', 'valid_until'}
    if not isinstance(command, dict) or set(command) - keys or command.get('version') != 2:
        raise ControlError('INVALID_COMMAND_SCHEMA')
    if command.get('operation') not in OPS:
        raise ControlError('INVALID_OPERATION')
    if not re.fullmatch(r'[a-f0-9]{32}', str(command.get('request_id', ''))):
        raise ControlError('INVALID_REQUEST_ID')
    if type(command.get('lifetime_seconds')) is not int or command['lifetime_seconds'] not in (3600, 7200, 10800):
        raise ControlError('INVALID_DURATION')
    name = command.get('codespace')
    if name is not None and (not isinstance(name, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,99}', name)):
        raise ControlError('INVALID_CODESPACE_NAME')
    issued, until = command.get('issued_at'), command.get('valid_until')
    if type(issued) is not int or type(until) is not int or not 0 < until - issued <= 3600:
        raise ControlError('INVALID_COMMAND_WINDOW')
    if issued > now + 60 or now >= until:
        raise ControlError('COMMAND_EXPIRED_OR_FROM_FUTURE')
    public_key(command.get('reply_public_key'))
    return command


def select(items: list[dict], name: str | None = None):
    items = [x for x in items if x.get('repository', {}).get('full_name', '').lower() == REPO]
    if name:
        matches = [x for x in items if x.get('name') == name]
        if len(matches) != 1:
            raise ControlError('NAMED_CODESPACE_NOT_FOUND')
        return matches[0]
    managed = [x for x in items if str(x.get('display_name', '')).startswith(TAG)]
    if len(managed) == 1:
        return managed[0]
    if len(managed) > 1 or len(items) > 1:
        raise ControlError('AMBIGUOUS_CODESPACE_SELECTION')
    return items[0] if items else None


def tagged_deadline(item: dict) -> int | None:
    m = re.fullmatch(re.escape(TAG) + r'([0-9]{10})', str(item.get('display_name', '')))
    return int(m.group(1)) if m else None


def seal(payload: dict, pem: str, request_id: str) -> dict:
    key = public_key(pem)
    aes = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    aad = ('blackcat-reply-v2:' + request_id).encode('ascii')
    raw = json.dumps(payload, separators=(',', ':')).encode()
    if len(raw) > 65536:
        raise ControlError('REPLY_TOO_LARGE')
    ciphertext = AESGCM(aes).encrypt(nonce, raw, aad)
    wrapped = key.encrypt(aes, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=aad))
    enc = lambda b: base64.b64encode(b).decode('ascii')
    return {'version': 2, 'request_id': request_id, 'algorithm': 'RSA-OAEP-SHA256+A256GCM',
            'wrapped_key': enc(wrapped), 'nonce': enc(nonce), 'ciphertext': enc(ciphertext)}


def unseal(envelope: dict, private_pem: bytes, expected_request: str) -> dict:
    """Used only by the requesting cloud chat runtime, never by the workflow."""
    if envelope.get('version') != 2 or envelope.get('request_id') != expected_request or envelope.get('algorithm') != 'RSA-OAEP-SHA256+A256GCM':
        raise ControlError('REPLY_ID_OR_VERSION_MISMATCH')
    dec = lambda s: base64.b64decode(s, validate=True)
    private = serialization.load_pem_private_key(private_pem, password=None)
    aad = ('blackcat-reply-v2:' + expected_request).encode('ascii')
    aes = private.decrypt(dec(envelope['wrapped_key']), padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=aad))
    return json.loads(AESGCM(aes).decrypt(dec(envelope['nonce']), dec(envelope['ciphertext']), aad))
