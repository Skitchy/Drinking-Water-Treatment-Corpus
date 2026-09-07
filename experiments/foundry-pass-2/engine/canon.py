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
import stat
import tempfile
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


# --- no-follow evidence-path primitives (discussioncomment-18321488,
# blocking finding 2; authorized by 18321531). Mutable evidence lives in
# untracked directories, so a git-clean tree says nothing about symlinks
# planted there. Every pre-existing evidence path is inspected with lstat,
# opened without following links, and rewritten only through a
# same-directory temporary regular file plus atomic replace.

class PathBoundaryError(OSError):
    """A path inside an evidence root is a symlink or an unexpected type."""


def is_regular(path):
    """True only for an existing regular file that is not a symlink."""
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except FileNotFoundError:
        return False


def is_real_dir(path):
    """True only for an existing directory that is not a symlink."""
    try:
        return stat.S_ISDIR(os.lstat(path).st_mode)
    except FileNotFoundError:
        return False


def refuse_unless_regular(path, what="path"):
    """lstat gate: the path must not exist, or must be a regular file."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return
    if not stat.S_ISREG(st.st_mode):
        kind = "symlink" if stat.S_ISLNK(st.st_mode) else "non-regular file"
        raise PathBoundaryError(f"{what} {path} is a {kind}; refusing")


def refuse_unless_real_dir(path, what="directory"):
    """lstat gate: the path must not exist, or must be a real directory."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return
    if not stat.S_ISDIR(st.st_mode):
        kind = "symlink" if stat.S_ISLNK(st.st_mode) else "non-directory"
        raise PathBoundaryError(f"{what} {path} is a {kind}; refusing")


def read_regular_bytes(path):
    """Read a pre-existing regular file without following a symlink at the
    final component, and verify the opened inode is the inspected one."""
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode):
        raise PathBoundaryError(f"{path} is not a regular file; refusing to read")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        after = os.fstat(fd)
        if (after.st_ino, after.st_dev) != (before.st_ino, before.st_dev):
            raise PathBoundaryError(f"{path} changed identity between lstat "
                                    "and open; refusing to read")
        chunks = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        os.close(fd)
    return b"".join(chunks)


def load_json_regular(path):
    return json.loads(read_regular_bytes(path).decode("utf-8"))


class ShortWriteError(OSError):
    """os.write returned a count that does not cover the bytes requested (a
    short, zero, negative, non-integer, or out-of-range count). The caller
    refuses to treat the destination as written."""


os_write = os.write  # single seam so tests can inject short writes


def write_all(fd, data, what="write"):
    """Persist every byte of `data` to `fd`, or raise.

    A successful os.write may legally return fewer bytes than requested
    without raising; one call that ignores the count can install a
    truncated file and report success with a digest of bytes that never
    reached disk (Ari, discussioncomment-18322012). This loops over a
    memoryview until the whole buffer is written and raises
    ShortWriteError on a zero, negative, non-integer, or out-of-range
    count so the caller fails closed."""
    view = memoryview(data).cast("B")
    total = len(view)
    written = 0
    while written < total:
        n = os_write(fd, view[written:])
        if (not isinstance(n, int) or isinstance(n, bool)
                or n <= 0 or n > total - written):
            raise ShortWriteError(
                f"{what}: os.write returned {n!r} with {total - written} "
                f"byte(s) remaining after {written} of {total}; refusing to "
                "treat the destination as written")
        written += n
    return written


def write_canonical_atomic(path, obj):
    """Canonical bytes to `path` via a same-directory temporary regular file,
    fsync, atomic replace, directory fsync. Every byte is written through
    write_all (a short or zero-byte os.write is a refusal, and the
    temporary file is removed, never installed). Refuses a destination that
    exists and is not a regular file (a symlink would otherwise be followed
    by open(..., 'wb') and its external target overwritten)."""
    refuse_unless_regular(path, "write destination")
    data = canonical_bytes(obj)
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=directory)
    try:
        write_all(fd, data, "write destination temporary file")
        os.fsync(fd)
        # the count os.write reports is an assertion by the writer; the
        # size the kernel reports after fsync is what actually landed
        on_disk = os.fstat(fd).st_size
        if on_disk != len(data):
            raise ShortWriteError(
                f"write destination temporary file: {on_disk} byte(s) on "
                f"disk for a {len(data)} byte payload after fsync; refusing "
                "to install the destination")
        os.close(fd)
        fd = None
        # the destination is re-inspected at the last moment; replace()
        # itself never follows a link, but a link would be deleted, not
        # written through, and the honest outcome is a refusal
        refuse_unless_regular(path, "write destination")
        os.replace(tmp, path)
    except BaseException:
        if fd is not None:
            os.close(fd)
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    dfd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
    return hashlib.sha256(data).hexdigest()
