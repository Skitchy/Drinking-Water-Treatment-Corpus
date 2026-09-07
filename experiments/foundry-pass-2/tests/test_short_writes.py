"""Short-write correction (Ari, discussioncomment-18322012; maintainer
authorization requested on that comment).

`canon.write_canonical_atomic()` and `reserve_head()` each called
`os.write(fd, data)` once and ignored its return value. A successful
`os.write` may legally persist fewer bytes than requested without
raising, so a short write installed a truncated file while the function
returned the SHA-256 of the full bytes. Both sites now write through
`canon.write_all()`, which loops over a memoryview until every byte is
written and raises `ShortWriteError` on a zero, negative, non-integer, or
out-of-range count, so the caller fails closed.

No test makes a model call. Every test writes only under temp
directories. Short writes are injected through the `canon.os_write` seam;
the real `os.write` is never replaced globally.
"""

import hashlib
import os
import shutil
import sys
import tempfile
import unittest

PASS2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PASS2)
sys.path.insert(0, os.path.join(PASS2, "tools"))

from engine import canon  # noqa: E402
import run_reviewer_a  # noqa: E402
try:
    from tests.test_qualify_at_most_once import _QualifyHarness, HEAD, FIXTURE_READY  # noqa: E402
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_qualify_at_most_once import _QualifyHarness, HEAD, FIXTURE_READY  # noqa: E402

REAL_WRITE = os.write


class ChunkedWriter:
    """os.write stand-in that persists at most `chunk` bytes per call and
    returns the legal short count. Records every call."""

    def __init__(self, chunk):
        self.chunk = chunk
        self.calls = []

    def __call__(self, fd, buf):
        # the primitive must hand the raw write a memoryview slice
        assert isinstance(buf, memoryview), type(buf)
        piece = bytes(buf[:self.chunk])
        n = REAL_WRITE(fd, piece)
        self.calls.append(n)
        return n


class ZeroAfter:
    """Persists the first `good` bytes honestly, then returns 0 (a legal
    successful os.write that wrote nothing) on every later call."""

    def __init__(self, good):
        self.good = good
        self.calls = []

    def __call__(self, fd, buf):
        if self.good > 0:
            n = REAL_WRITE(fd, bytes(memoryview(buf)[:self.good]))
            self.good = 0
            self.calls.append(n)
            return n
        self.calls.append(0)
        return 0


class LyingWriter:
    """Persists `real` bytes but reports `claimed` (an out-of-range count)."""

    def __init__(self, real, claimed):
        self.real, self.claimed = real, claimed

    def __call__(self, fd, buf):
        REAL_WRITE(fd, bytes(memoryview(buf)[:self.real]))
        return self.claimed


class ShortThenOverclaim:
    """First call is a legal short write of `first` bytes; the next call
    reports a count larger than the bytes REMAINING but not larger than
    the whole payload. This is the case that separates `n > total -
    written` from the off-by-one `n > total` (adversary finding F1)."""

    def __init__(self, first):
        self.first = first
        self.calls = 0
        self.total = None

    def __call__(self, fd, buf):
        self.calls += 1
        if self.calls == 1:
            self.total = len(buf)  # the whole payload on call 1
            return REAL_WRITE(fd, bytes(buf[:self.first]))
        # remaining == total - first; claim exactly `total`, which is
        # in range for a guard against the whole payload and out of range
        # for a guard against the remainder
        REAL_WRITE(fd, bytes(buf[:1]))
        return self.total


class InRangeLiar:
    """Persists fewer bytes than it reports, but every reported count is
    within the remaining range, so the counts alone look honest and sum
    exactly to the payload (adversary finding F2). Only the size on disk
    exposes it."""

    def __init__(self, real, claim):
        self.real, self.claim = real, claim

    def __call__(self, fd, buf):
        remaining = len(buf)
        REAL_WRITE(fd, bytes(buf[:min(self.real, remaining)]))
        return min(self.claim, remaining)


class Errno28:
    def __call__(self, fd, buf):
        raise OSError(28, "No space left on device")


class _SeamCase(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="shortwrite-")
        self.saved_write = canon.os_write

    def tearDown(self):
        canon.os_write = self.saved_write
        shutil.rmtree(self.d)

    def leftovers(self, directory=None):
        return sorted(f for f in os.listdir(directory or self.d) if f.startswith(".tmp-"))


class WriteAllPrimitive(_SeamCase):
    def test_short_writes_are_retried_until_every_byte_lands(self):
        data = bytes(range(256)) * 3
        path = os.path.join(self.d, "raw.bin")
        writer = ChunkedWriter(chunk=100)
        canon.os_write = writer
        fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o644)
        try:
            self.assertEqual(canon.write_all(fd, data, "test"), len(data))
        finally:
            os.close(fd)
        self.assertEqual(writer.calls, [100, 100, 100, 100, 100, 100, 100, 68])
        with open(path, "rb") as f:
            self.assertEqual(f.read(), data)

    def test_zero_count_raises(self):
        fd = os.open(os.path.join(self.d, "z.bin"), os.O_WRONLY | os.O_CREAT, 0o644)
        try:
            canon.os_write = ZeroAfter(good=0)
            with self.assertRaises(canon.ShortWriteError) as ctx:
                canon.write_all(fd, b"abcdef", "test")
        finally:
            os.close(fd)
        self.assertIn("returned 0", str(ctx.exception))
        self.assertIn("6 byte(s) remaining after 0 of 6", str(ctx.exception))

    def test_out_of_range_count_raises(self):
        fd = os.open(os.path.join(self.d, "o.bin"), os.O_WRONLY | os.O_CREAT, 0o644)
        try:
            canon.os_write = LyingWriter(real=2, claimed=99)
            with self.assertRaises(canon.ShortWriteError):
                canon.write_all(fd, b"abcdef", "test")
            canon.os_write = lambda fd, buf: -1
            with self.assertRaises(canon.ShortWriteError):
                canon.write_all(fd, b"abcdef", "test")
            canon.os_write = lambda fd, buf: None
            with self.assertRaises(canon.ShortWriteError):
                canon.write_all(fd, b"abcdef", "test")
            canon.os_write = lambda fd, buf: True
            with self.assertRaises(canon.ShortWriteError):
                canon.write_all(fd, b"abcdef", "test")
        finally:
            os.close(fd)

    def test_short_write_error_is_an_oserror(self):
        self.assertTrue(issubclass(canon.ShortWriteError, OSError))

    def test_overclaim_relative_to_remaining_raises_after_a_short_write(self):
        """Adversary F1: a legal short write followed by a count that is
        larger than the REMAINDER but not larger than the whole payload
        must refuse. A guard that compares against the whole payload
        instead of the remainder accepts it."""
        fd = os.open(os.path.join(self.d, "f1.bin"), os.O_WRONLY | os.O_CREAT, 0o644)
        try:
            writer = ShortThenOverclaim(first=17)
            canon.os_write = writer
            with self.assertRaises(canon.ShortWriteError) as ctx:
                canon.write_all(fd, bytes(range(149)), "test")
        finally:
            os.close(fd)
        self.assertEqual(writer.calls, 2)
        self.assertIn("returned 149 with 132 byte(s) remaining after 17 of 149", str(ctx.exception))


class AtomicWriterUnderShortWrites(_SeamCase):
    OBJ = {"artifact_version": "test/v0", "records": [{"id": i, "text": "x" * 40} for i in range(20)]}

    def test_forced_short_writes_install_byte_for_byte_canonical_bytes(self):
        """Finding 1 of 18322012: several short writes; the installed file
        is byte-for-byte canonical and the returned digest matches it."""
        path = os.path.join(self.d, "manifest.json")
        expected = canon.canonical_bytes(self.OBJ)
        writer = ChunkedWriter(chunk=23)
        canon.os_write = writer
        digest = canon.write_canonical_atomic(path, self.OBJ)
        self.assertGreater(len(writer.calls), 1)
        self.assertEqual(sum(writer.calls), len(expected))
        with open(path, "rb") as f:
            on_disk = f.read()
        self.assertEqual(on_disk, expected)
        self.assertEqual(digest, hashlib.sha256(on_disk).hexdigest())
        self.assertEqual(self.leftovers(), [])
        # the re-read path agrees
        self.assertEqual(canon.load_json_regular(path), self.OBJ)

    def test_one_byte_writes_still_install_the_whole_file(self):
        path = os.path.join(self.d, "one.json")
        expected = canon.canonical_bytes(self.OBJ)
        canon.os_write = ChunkedWriter(chunk=1)
        digest = canon.write_canonical_atomic(path, self.OBJ)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), expected)
        self.assertEqual(digest, hashlib.sha256(expected).hexdigest())

    def test_zero_byte_return_refuses_and_installs_nothing_fresh(self):
        """Finding 2 of 18322012: a zero-byte return refuses; no
        destination is installed and no temporary file is left behind."""
        path = os.path.join(self.d, "fresh.json")
        canon.os_write = ZeroAfter(good=23)
        with self.assertRaises(canon.ShortWriteError):
            canon.write_canonical_atomic(path, self.OBJ)
        self.assertFalse(os.path.lexists(path))
        self.assertEqual(self.leftovers(), [])

    def test_zero_byte_return_leaves_existing_destination_untouched(self):
        path = os.path.join(self.d, "existing.json")
        prior = canon.canonical_bytes({"prior": True})
        with open(path, "wb") as f:
            f.write(prior)
        before = os.stat(path)
        canon.os_write = ZeroAfter(good=5)
        with self.assertRaises(canon.ShortWriteError):
            canon.write_canonical_atomic(path, self.OBJ)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), prior)
        self.assertEqual(os.stat(path).st_ino, before.st_ino)
        self.assertEqual(self.leftovers(), [])

    def test_out_of_range_count_refuses_and_installs_nothing(self):
        path = os.path.join(self.d, "lying.json")
        canon.os_write = LyingWriter(real=10, claimed=10 ** 6)
        with self.assertRaises(canon.ShortWriteError):
            canon.write_canonical_atomic(path, self.OBJ)
        self.assertFalse(os.path.lexists(path))
        self.assertEqual(self.leftovers(), [])

    def test_short_write_then_overclaim_installs_nothing(self):
        """Adversary F1 through the atomic writer."""
        path = os.path.join(self.d, "f1.json")
        canon.os_write = ShortThenOverclaim(first=17)
        with self.assertRaises(canon.ShortWriteError):
            canon.write_canonical_atomic(path, self.OBJ)
        self.assertFalse(os.path.lexists(path))
        self.assertEqual(self.leftovers(), [])

    def test_in_range_lie_is_caught_by_the_size_on_disk(self):
        """Adversary F2: every reported count is in range and the counts
        sum to the payload, but fewer bytes landed. The size the kernel
        reports after fsync is checked against the payload, so the
        destination is never installed and no digest is returned."""
        path = os.path.join(self.d, "f2.json")
        canon.os_write = InRangeLiar(real=1, claim=5)
        with self.assertRaises(canon.ShortWriteError) as ctx:
            canon.write_canonical_atomic(path, self.OBJ)
        self.assertIn("byte(s) on disk for a", str(ctx.exception))
        self.assertFalse(os.path.lexists(path))
        self.assertEqual(self.leftovers(), [])

    def test_in_range_lie_leaves_existing_destination_untouched(self):
        path = os.path.join(self.d, "f2b.json")
        prior = canon.canonical_bytes({"prior": 2})
        with open(path, "wb") as f:
            f.write(prior)
        canon.os_write = InRangeLiar(real=3, claim=9)
        with self.assertRaises(canon.ShortWriteError):
            canon.write_canonical_atomic(path, self.OBJ)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), prior)
        self.assertEqual(self.leftovers(), [])

    def test_partial_bytes_never_reach_the_destination_name(self):
        """Under a zero return the partial bytes exist only in the
        unlinked temporary file; the destination name is never created."""
        path = os.path.join(self.d, "never.json")
        seen = []
        real_replace = os.replace

        def spy_replace(src, dst):
            seen.append(dst)
            return real_replace(src, dst)
        canon.os_write = ZeroAfter(good=1)
        saved = os.replace
        os.replace = spy_replace
        try:
            with self.assertRaises(canon.ShortWriteError):
                canon.write_canonical_atomic(path, self.OBJ)
        finally:
            os.replace = saved
        self.assertEqual(seen, [])
        self.assertFalse(os.path.lexists(path))


class ReservationUnderShortWrites(_SeamCase):
    """Finding 3 of 18322012: the exact-head reservation gets the same
    short-write check."""

    def test_short_writes_still_produce_a_complete_canonical_reservation(self):
        q = os.path.join(self.d, "q")
        writer = ChunkedWriter(chunk=17)
        canon.os_write = writer
        path = run_reviewer_a.reserve_head(q, HEAD, {"reserved_utc": "t", "model_id": "fake"})
        self.assertGreater(len(writer.calls), 1)
        with open(path, "rb") as f:
            on_disk = f.read()
        expected = canon.canonical_bytes({
            "reserved_utc": "t", "model_id": "fake",
            "artifact_version": "foundry-pass-2-qualification-reservation/experimental-v0.1",
            "head": HEAD})
        self.assertEqual(on_disk, expected)
        self.assertEqual(canon.load_json(path)["head"], HEAD)

    def test_zero_byte_return_refuses_before_any_session_and_keeps_the_head_spent(self):
        q = os.path.join(self.d, "q")
        canon.os_write = ZeroAfter(good=9)
        with self.assertRaises(SystemExit) as ctx:
            run_reviewer_a.reserve_head(q, HEAD, {"reserved_utc": "t"})
        msg = str(ctx.exception)
        self.assertIn("qualification refused", msg)
        self.assertIn("could not be durably written", msg)
        self.assertIn("no session was constructed", msg)
        path = run_reviewer_a.reservation_path(q, HEAD)
        # the exclusive file exists (partial bytes) and stays authoritative
        self.assertTrue(os.path.isfile(path))
        canon.os_write = self.saved_write
        with self.assertRaises(SystemExit) as ctx2:
            run_reviewer_a.reserve_head(q, HEAD, {"reserved_utc": "t2"})
        self.assertIn("already reserved", str(ctx2.exception))


    def test_in_range_lie_refuses_the_reservation(self):
        """Adversary F2 on the reservation: counts look honest, the size
        on disk after fsync does not; refused, head stays spent."""
        q = os.path.join(self.d, "q")
        canon.os_write = InRangeLiar(real=2, claim=7)
        with self.assertRaises(SystemExit) as ctx:
            run_reviewer_a.reserve_head(q, HEAD, {"reserved_utc": "t"})
        self.assertIn("could not be durably written", str(ctx.exception))
        self.assertIn("on disk for a", str(ctx.exception))
        self.assertTrue(os.path.isfile(run_reviewer_a.reservation_path(q, HEAD)))

    def test_other_oserror_during_the_reservation_write_is_a_refusal(self):
        """Adversary F3: an errno failure from the raw write refuses in
        the same words as a short write; the head stays spent."""
        q = os.path.join(self.d, "q")
        canon.os_write = Errno28()
        with self.assertRaises(SystemExit) as ctx:
            run_reviewer_a.reserve_head(q, HEAD, {"reserved_utc": "t"})
        msg = str(ctx.exception)
        self.assertIn("qualification refused", msg)
        self.assertIn("No space left on device", msg)
        path = run_reviewer_a.reservation_path(q, HEAD)
        self.assertTrue(os.path.isfile(path))
        self.assertEqual(os.path.getsize(path), 0)
        canon.os_write = self.saved_write
        with self.assertRaises(SystemExit) as ctx2:
            run_reviewer_a.reserve_head(q, HEAD, {"reserved_utc": "t2"})
        self.assertIn("already reserved", str(ctx2.exception))

    def test_refusal_path_fsyncs_the_partial_reservation_and_its_directory(self):
        """Adversary F5: the spent state must survive a crash right after
        the refusal, so the partial file and its directory are fsynced
        before SystemExit."""
        q = os.path.join(self.d, "q")
        synced = []
        real_fsync = os.fsync

        def spy_fsync(fd):
            synced.append(os.fstat(fd).st_mode)
            return real_fsync(fd)
        canon.os_write = ZeroAfter(good=9)
        os.fsync = spy_fsync
        try:
            with self.assertRaises(SystemExit):
                run_reviewer_a.reserve_head(q, HEAD, {"reserved_utc": "t"})
        finally:
            os.fsync = real_fsync
        import stat as _stat
        kinds = sorted("dir" if _stat.S_ISDIR(m) else "file" for m in synced)
        self.assertEqual(kinds, ["dir", "file"])


    def test_interrupt_inside_the_reservation_write_fsyncs_then_propagates(self):
        """Adversary pass-two G2: an operator interrupt during the raw write
        must leave the spent state durable (both fsyncs) before it
        propagates; the head refuses on the next command."""
        q = os.path.join(self.d, "q")
        synced = []
        real_fsync = os.fsync

        def spy_fsync(fd):
            synced.append(os.fstat(fd).st_mode)
            return real_fsync(fd)

        class Interrupt:
            def __call__(self, fd, buf):
                REAL_WRITE(fd, bytes(buf[:9]))
                raise KeyboardInterrupt("^C during the reservation write")
        canon.os_write = Interrupt()
        os.fsync = spy_fsync
        try:
            with self.assertRaises(KeyboardInterrupt):
                run_reviewer_a.reserve_head(q, HEAD, {"reserved_utc": "t"})
        finally:
            os.fsync = real_fsync
        import stat as _stat
        kinds = sorted("dir" if _stat.S_ISDIR(m) else "file" for m in synced)
        self.assertEqual(kinds, ["dir", "file"])
        path = run_reviewer_a.reservation_path(q, HEAD)
        self.assertTrue(os.path.isfile(path))
        self.assertEqual(os.path.getsize(path), 9)
        canon.os_write = self.saved_write
        with self.assertRaises(SystemExit) as ctx2:
            run_reviewer_a.reserve_head(q, HEAD, {"reserved_utc": "t2"})
        self.assertIn("already reserved", str(ctx2.exception))

    def test_directory_fsync_failure_after_a_complete_write_is_a_refusal(self):
        """Adversary pass-two G3: the success-path directory fsync fails;
        the reservation is complete and file-fsynced, and the outcome is a
        refusal in the harness's words, not a raw traceback."""
        q = os.path.join(self.d, "q")
        real_fsync = os.fsync
        import stat as _stat

        def failing_dir_fsync(fd):
            if _stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError(5, "injected directory fsync failure")
            return real_fsync(fd)
        os.fsync = failing_dir_fsync
        try:
            with self.assertRaises(SystemExit) as ctx:
                run_reviewer_a.reserve_head(q, HEAD, {"reserved_utc": "t"})
        finally:
            os.fsync = real_fsync
        msg = str(ctx.exception)
        self.assertIn("qualification refused", msg)
        self.assertIn("directory could not be fsynced", msg)
        path = run_reviewer_a.reservation_path(q, HEAD)
        self.assertEqual(canon.load_json(path)["head"], HEAD)

    def test_file_fsync_failure_after_a_complete_write_names_durability_not_bytes(self):
        """Adversary pass-two G4: every byte landed but fsync failed; the
        refusal must not claim the record was not fully written."""
        q = os.path.join(self.d, "q")
        real_fsync = os.fsync
        import stat as _stat
        calls = []

        def failing_file_fsync(fd):
            if _stat.S_ISREG(os.fstat(fd).st_mode) and not calls:
                calls.append(1)
                raise OSError(5, "injected file fsync failure")
            return real_fsync(fd)
        os.fsync = failing_file_fsync
        try:
            with self.assertRaises(SystemExit) as ctx:
                run_reviewer_a.reserve_head(q, HEAD, {"reserved_utc": "t"})
        finally:
            os.fsync = real_fsync
        msg = str(ctx.exception)
        self.assertIn("could not be durably written", msg)
        self.assertNotIn("not fully written", msg)
        path = run_reviewer_a.reservation_path(q, HEAD)
        self.assertEqual(canon.load_json(path)["head"], HEAD)


@unittest.skipUnless(FIXTURE_READY, "public fixture not emitted")
class QualifyRefusesOnReservationShortWrite(_QualifyHarness):
    """The whole qualification command, with the zero return injected at
    the reservation: refused before any session exists, and the head is
    refused again on the next command."""

    def setUp(self):
        super().setUp()
        self.saved_write = canon.os_write

    def tearDown(self):
        canon.os_write = self.saved_write
        super().tearDown()

    def test_zero_byte_reservation_write_refuses_with_zero_sessions(self):
        canon.os_write = ZeroAfter(good=7)
        exc = self.qualify()
        self.assertIn("qualification refused", str(exc))
        self.assertIn("could not be durably written", str(exc))
        self.assertEqual(len(self.sessions), 0)
        self.assertTrue(os.path.isfile(run_reviewer_a.reservation_path(self.q, HEAD)))
        self.assertFalse(os.path.isfile(os.path.join(self.q, "qualification-ledger.json")))
        canon.os_write = self.saved_write
        self.assert_refused(self.qualify(), "reservation")
        self.assertEqual(len(self.sessions), 0)

    def test_short_reservation_writes_do_not_change_the_governed_path(self):
        canon.os_write = ChunkedWriter(chunk=11)
        self.assertEqual(self.qualify().code, 0)
        self.assertEqual(len(self.sessions), 1)
        res = canon.load_json(run_reviewer_a.reservation_path(self.q, HEAD))
        self.assertEqual(res["head"], HEAD)


if __name__ == "__main__":
    unittest.main()
