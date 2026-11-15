# -*- coding: utf-8 -*-
"""AES-256-GCM 원본 파일 암호화. 키는 data_local/secret.key (출력 금지)."""
from __future__ import annotations

import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

APP = Path(__file__).resolve().parents[1]
KEY_PATH = APP / "data_local" / "secret.key"


def _load_or_create_key() -> bytes:
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if KEY_PATH.exists():
        key = KEY_PATH.read_bytes()
        if len(key) != 32:
            raise RuntimeError("secret.key length invalid")
        return key
    key = os.urandom(32)
    KEY_PATH.write_bytes(key)
    try:
        os.chmod(KEY_PATH, 0o600)
    except Exception:
        pass
    return key


def encrypt_bytes(plain: bytes) -> tuple[bytes, bytes]:
    """returns (nonce, ciphertext)."""
    key = _load_or_create_key()
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plain, None)
    return nonce, ct


def decrypt_bytes(nonce: bytes, ciphertext: bytes) -> bytes:
    key = _load_or_create_key()
    return AESGCM(key).decrypt(nonce, ciphertext, None)
