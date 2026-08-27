"""Shared deterministic primitives for the Foundry Pass 1 compiler.

Canonical byte profile (brief section 7): UTF-8, LF, sorted keys, compact
separators, one trailing LF. Content digests are sha256 over exactly those
bytes. Nothing in this module reads the clock or any other ambient state.
"""

import hashlib
import json
import os
import unicodedata


def canonical_bytes(obj):
    """Serialize obj to the declared canonical JSON byte profile."""
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def content_digest(obj):
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_text(raw):
    """Declared text normalization: NFC, whitespace runs to single space,
    stripped. Returns '' for None."""
    if raw is None:
        return ""
    return " ".join(unicodedata.normalize("NFC", raw).split())


def write_canonical(path, obj):
    """Write a canonical payload file and return its digest."""
    data = canonical_bytes(obj)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return hashlib.sha256(data).hexdigest()


class CaptureVerificationError(Exception):
    """A closed-input member failed verification. Fail closed: the caller
    must emit nothing downstream for this member."""


def verify_member(repo_root, member):
    """Verify one input-manifest member by existence, byte length, sha256.

    Returns a per-member verification record (class-1 payload shape).
    Raises CaptureVerificationError on any mismatch.
    """
    path = os.path.join(repo_root, member["path"])
    if not os.path.isfile(path):
        raise CaptureVerificationError(
            f"missing member: {member['path']}")
    actual_len = os.path.getsize(path)
    if actual_len != member["byte_length"]:
        raise CaptureVerificationError(
            f"byte length mismatch for {member['path']}: "
            f"manifest {member['byte_length']}, actual {actual_len}")
    actual_sha = file_sha256(path)
    if actual_sha != member["sha256"]:
        raise CaptureVerificationError(
            f"sha256 mismatch for {member['path']}: "
            f"manifest {member['sha256']}, actual {actual_sha}")
    return {
        "member_path": member["path"],
        "byte_length": member["byte_length"],
        "sha256": member["sha256"],
        "verdict": "verified",
    }


def verify_input_bundle(repo_root, manifest):
    """Stage 0 over the whole closed input. Returns (records, failures).

    Fail-closed is per member: failures carry the exception message and the
    member emits nothing downstream; verified members proceed.
    """
    records, failures = [], []
    for member in manifest["members"]:
        try:
            records.append(verify_member(repo_root, member))
        except CaptureVerificationError as err:
            failures.append({
                "member_path": member["path"],
                "verdict": "failed-closed",
                "reason": str(err),
            })
    return records, failures


def chained_append(log_path, entry, prev_head):
    """Append-only failure log: JSON line whose head chains the previous.

    Returns the new head digest. entry must be a canonical-serializable dict.
    """
    body = {"entry": entry, "prev_head": prev_head}
    head = content_digest(body)
    line = json.dumps({"head": head, **body}, ensure_ascii=False,
                      sort_keys=True, separators=(",", ":"))
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    return head
