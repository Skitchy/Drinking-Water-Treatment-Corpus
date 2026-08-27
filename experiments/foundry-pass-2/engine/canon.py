"""Canonical byte profile shared by every Foundry artifact (Pass 1 brief
section 7; Ari's reviewer contract "canonicalization"): UTF-8, NFC strings,
sorted keys, compact separators, LF, exactly one trailing LF. Content
digests are sha256 over exactly those bytes.

Deliberately duplicated from the Pass 1 compiler's foundry_lib rather than
imported: the engine must not depend on any adapter-side tree, and the
profile is a declared contract, not shared code.
"""

import hashlib
import json
import os
import unicodedata


def nfc(value):
    """Recursively NFC-normalize every string in a JSON value."""
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [nfc(v) for v in value]
    if isinstance(value, dict):
        return {nfc(k): nfc(v) for k, v in value.items()}
    return value


def canonical_bytes(obj):
    text = json.dumps(nfc(obj), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def content_digest(obj):
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def bytes_digest(data):
    return hashlib.sha256(data).hexdigest()


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_canonical(path, obj):
    data = canonical_bytes(obj)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return hashlib.sha256(data).hexdigest()


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)
