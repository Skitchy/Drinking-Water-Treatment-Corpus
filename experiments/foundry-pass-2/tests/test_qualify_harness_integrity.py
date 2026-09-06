"""Harness-integrity correction authorized by maintainer ruling 18321531 in
response to Ari's exact-diff disposition of d3db7a0 (discussioncomment-
18321488, two blocking findings):

1. Interrupt accounting. `run_leak_probes.call()` caught `Exception`, so a
   `KeyboardInterrupt` raised inside `session.run()` skipped the two lines
   that copy the live invocation count into the transcript entry;
   `qualify()` finalized FAIL and published `invocations 0` for a call
   that may have reached the model. Now every `BaseException` leaving the
   model call copies the live accounting into the entry and persists it
   BEFORE the attempt is finalized FAIL, and an interrupt between calls
   is finalized FAIL with the accounting the entries already hold.

2. No-follow evidence paths. `append_ledger()` wrote through
   `open(..., "wb")`, which follows a symlink and overwrites its external
   target; `stash_stale_transcript()` read a symlinked working transcript
   through and copied external bytes into the qualification root. Now a
   path-boundary gate inspects the root, its ancestors below the pass
   root, the reservations directory, and every pre-existing evidence entry
   with lstat BEFORE any reservation is written or any evidence is read;
   pre-existing inputs are opened without following links and checked by
   inode; mutable manifests and the ledger are written through a
   same-directory temporary regular file, fsync, and atomic replace.

No test makes a model call. Every test writes only under temp
directories, and the tests that plant symlinks verify the external
target was neither read nor modified.
"""

import os
import shutil
import sys
import tempfile
import unittest

PASS2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PASS2)
sys.path.insert(0, os.path.join(PASS2, "tools"))

from engine import canon, reviewer  # noqa: E402
import run_reviewer_a  # noqa: E402
try:
    from tests.test_self_adversarial_89a56c9 import ConformantSession, _accept  # noqa: E402
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_self_adversarial_89a56c9 import ConformantSession, _accept  # noqa: E402

FIXTURE = os.environ.get("FOUNDRY_PASS2_OUT", os.path.join(PASS2, "out-fixture"))
FIXTURE_READY = os.path.isfile(os.path.join(FIXTURE, "review-input-bundle.json"))
HEAD = "d" * 40

SAVED_KEYS = ("Q_OUT", "git_head", "make_session", "schema_validator",
              "FIXTURE_OUT", "MODEL", "cli_version", "write_attempt_record",
              "append_ledger")


class InterruptedSession(ConformantSession):
    """A one-attempt session that starts a real invocation (an independent
    counter proves it), reports it live the way IsolatedSession does, then
    is interrupted before it can return. `interrupt_on` names the logical
    call (1-based) that is interrupted; earlier calls complete normally."""

    def __init__(self, interrupt_on=1, exc=KeyboardInterrupt):
        super().__init__()
        self.interrupt_on = interrupt_on
        self.exc = exc
        self.real_invocations = 0  # the binary's own count, in the fake

    def run(self, prompt):
        if self.calls + 1 == self.interrupt_on:
            self.calls += 1
            self.real_invocations += 1
            self.last_invocations = 1  # live: an invocation has started
            self.last_invocation_log = [{"invocation": 1,
                                         "outcome": "interrupted"}]
            raise self.exc()
        result = super().run(prompt)
        self.real_invocations += 1
        return result


class TotalCountingSession(InterruptedSession):
    """InterruptedSession that also keeps IsolatedSession's cumulative
    `total_invocations`. `reset_before_interrupt` reproduces the real
    class's reset window (per-call counter already zeroed, no invocation
    started yet); `stale_counter` reproduces an interrupt before the reset
    (per-call counter still holds the previous call's value)."""

    def __init__(self, interrupt_on=1, exc=KeyboardInterrupt,
                 reset_before_interrupt=False, stale_counter=False):
        super().__init__(interrupt_on, exc)
        self.total_invocations = 0
        self.reset_before_interrupt = reset_before_interrupt
        self.stale_counter = stale_counter
        self.on_interrupt = None

    def run(self, prompt):
        if self.calls + 1 == self.interrupt_on:
            self.calls += 1
            if self.reset_before_interrupt:
                self.last_invocations = 0
                self.last_invocation_log = []
            elif self.stale_counter:
                pass  # previous call's values still on the session
            else:
                self.real_invocations += 1
                self.total_invocations += 1
                self.last_invocations = 1
                self.last_invocation_log = [{"invocation": 1,
                                             "outcome": "interrupted"}]
            if self.on_interrupt:
                self.on_interrupt()
            raise self.exc()
        self.last_invocations = 0
        result = ConformantSession.run(self, prompt)
        self.real_invocations += 1
        self.total_invocations += 1
        return result


class _Harness(unittest.TestCase):
    def setUp(self):
        self.q = tempfile.mkdtemp(prefix="hi-")
        self.saved = {k: getattr(run_reviewer_a, k) for k in SAVED_KEYS}
        run_reviewer_a.Q_OUT = self.q
        run_reviewer_a.FIXTURE_OUT = FIXTURE
        run_reviewer_a.MODEL = "fake"
        run_reviewer_a.git_head = lambda: (HEAD, True)
        run_reviewer_a.cli_version = lambda: "fake-cli"
        run_reviewer_a.schema_validator = _accept
        os.environ["FOUNDRY_QUALIFY_RULED_MODEL"] = "fake"
        self.sessions = []

        def make(system_prompt, cwd, attempts=3):
            s = ConformantSession()
            s.attempts = attempts
            self.sessions.append(s)
            return s
        run_reviewer_a.make_session = make

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(run_reviewer_a, k, v)
        os.environ.pop("FOUNDRY_QUALIFY_RULED_MODEL", None)
        shutil.rmtree(self.q)

    def use_session(self, session):
        def make(system_prompt, cwd, attempts=3):
            session.attempts = attempts
            self.sessions.append(session)
            return session
        run_reviewer_a.make_session = make

    def qualify(self):
        with self.assertRaises(SystemExit) as ctx:
            run_reviewer_a.qualify()
        return ctx.exception

    def ledger(self):
        return canon.load_json(os.path.join(self.q, "qualification-ledger.json"))

    def records(self):
        return [canon.load_json(os.path.join(self.q, f))
                for f in sorted(os.listdir(self.q))
                if f.startswith("qualification-attempt-")]


@unittest.skipUnless(FIXTURE_READY, "public fixture not emitted")
class InterruptAccounting(_Harness):
    """18321488 blocking finding 1."""

    def test_interrupt_in_first_probe_is_ledgered_with_its_invocation(self):
        # Ari's reproduction (18321488): a one-attempt session that starts
        # a real invocation, reports it live, then raises KeyboardInterrupt.
        # Before the fix: ledger calls 0 | invocations 0 | session-reported.
        s = InterruptedSession(interrupt_on=1)
        self.use_session(s)
        exc = self.qualify()   # qualify() finalizes an interrupted attempt as FAIL
        self.assertEqual(exc.code, 1)
        self.assertEqual(s.real_invocations, 1)
        self.assertTrue(os.path.isfile(run_reviewer_a.reservation_path(self.q, HEAD)))
        entry = self.ledger()["attempts"][0]
        self.assertEqual(entry["result"], "FAIL")
        self.assertEqual(entry["model_calls"], 0)
        self.assertEqual(entry["cli_invocations"], 1)   # the spent invocation
        self.assertEqual(entry["invocation_accounting"], "session-reported")
        evidence = canon.load_json(os.path.join(self.q, entry["evidence_path"]))
        self.assertEqual(evidence["preflight_result"], "FAIL")
        self.assertEqual(len(evidence["transcripts"]), 1)
        self.assertEqual(evidence["transcripts"][0]["cli_invocations"], 1)
        self.assertEqual(evidence["transcripts"][0]["cli_invocation_log"][0]["outcome"],
                         "interrupted")
        self.assertIsNone(evidence["transcripts"][0]["result"])
        self.assertIn("KeyboardInterrupt", evidence["session_error"])
        self.assertIn("KeyboardInterrupt", self.records()[0]["error"])
        # second command at the same head: refused, no new session
        exc2 = self.qualify()
        self.assertIn("is spent", str(exc2))
        self.assertEqual(len(self.sessions), 1)

    def test_interrupt_caught_by_qualify_publishes_the_live_count_not_zero(self):
        # the same interrupt, but delivered as an ordinary BaseException
        # subclass that qualify()'s own handler converts to a ledgered FAIL
        # (GeneratorExit stands in: a BaseException that is not an
        # Exception and is not the operator's signal)
        s = InterruptedSession(interrupt_on=1, exc=GeneratorExit)
        self.use_session(s)
        exc = self.qualify()
        self.assertEqual(exc.code, 1)
        entry = self.ledger()["attempts"][0]
        self.assertEqual(entry["result"], "FAIL")
        self.assertEqual(entry["model_calls"], 0)
        self.assertEqual(entry["cli_invocations"], 1)   # was 0 before the fix
        self.assertEqual(entry["invocation_accounting"], "session-reported")
        self.assertEqual(s.real_invocations, 1)
        record = self.records()[0]
        self.assertEqual(record["cli_invocations"], 1)
        self.assertIn("GeneratorExit", record["error"])

    def test_interrupt_in_second_probe_keeps_the_first_call_and_counts_the_second(self):
        s = InterruptedSession(interrupt_on=2, exc=GeneratorExit)
        self.use_session(s)
        exc = self.qualify()
        self.assertEqual(exc.code, 1)
        entry = self.ledger()["attempts"][0]
        self.assertEqual(entry["result"], "FAIL")
        self.assertEqual(entry["model_calls"], 1)       # first call completed
        self.assertEqual(entry["cli_invocations"], 2)   # plus the interrupted one
        self.assertEqual(s.real_invocations, 2)
        evidence = canon.load_json(os.path.join(self.q, entry["evidence_path"]))
        self.assertEqual([t["cli_invocations"] for t in evidence["transcripts"]], [1, 1])
        self.assertIsNotNone(evidence["transcripts"][0]["result"])
        self.assertIsNone(evidence["transcripts"][1]["result"])
        # no double count: the first entry's accounting is untouched
        self.assertEqual(evidence["transcripts"][0]["cli_invocation_log"][0]["outcome"], "fake")

    def test_interrupt_between_calls_is_finalized_fail_with_existing_accounting(self):
        # interrupt raised by the validator after the first model call
        def interrupting_validator(output):
            raise GeneratorExit()
        run_reviewer_a.schema_validator = interrupting_validator
        exc = self.qualify()
        self.assertEqual(exc.code, 1)
        entry = self.ledger()["attempts"][0]
        self.assertEqual(entry["result"], "FAIL")
        self.assertEqual(entry["model_calls"], 1)
        self.assertEqual(entry["cli_invocations"], 1)
        evidence = canon.load_json(os.path.join(self.q, entry["evidence_path"]))
        self.assertIn("interrupted during preflight", evidence["failure_reason"])
        self.assertIn("GeneratorExit", evidence["session_error"])

    def test_f1_handler_interrupted_before_the_copy_still_publishes_the_live_count(self):
        # isolated adversary, second pass on this correction, F1: a second
        # interrupt delivered inside the handler BEFORE the accounting copy
        # left the on-disk entry at zero and the receipt said
        # `invocations 0 | session-reported`. The receipt is now reconciled
        # against the live session object, which still holds the count.
        s = InterruptedSession(interrupt_on=1)
        self.use_session(s)
        saved = reviewer.invocation_accounting
        state = {"armed": True}

        def second_interrupt(session, total_before=None):
            if state["armed"]:
                state["armed"] = False
                raise KeyboardInterrupt()   # inside the handler, before the copy
            return saved(session, total_before)
        reviewer.invocation_accounting = second_interrupt
        try:
            exc = self.qualify()
        finally:
            reviewer.invocation_accounting = saved
        self.assertEqual(exc.code, 1)
        self.assertEqual(s.real_invocations, 1)
        entry = self.ledger()["attempts"][0]
        self.assertEqual(entry["result"], "FAIL")
        self.assertEqual(entry["model_calls"], 0)
        self.assertEqual(entry["cli_invocations"], 1)   # never zero with session-reported
        # the second interrupt escaped through the outer handler, which now
        # refreshes the in-flight entry before finalizing FAIL, so the
        # durable sibling itself carries the count and nothing is left for
        # qualify() to reconcile
        evidence = canon.load_json(os.path.join(self.q, entry["evidence_path"]))
        self.assertEqual(evidence["preflight_result"], "FAIL")
        self.assertEqual(evidence["transcripts"][0]["cli_invocations"], 1)
        self.assertEqual(entry["invocation_accounting"], "session-reported")
        self.assertIsNone(entry["invocation_reconciliation"])

    def test_f1_reconciliation_fires_when_every_handler_copy_is_defeated(self):
        # the receipt-level floor on its own: every copy into the transcript
        # is defeated (the accounting function always says zero), the disk
        # says zero, the live session says one; the receipt must say one
        s = InterruptedSession(interrupt_on=1)
        self.use_session(s)
        saved = reviewer.invocation_accounting
        reviewer.invocation_accounting = lambda session, total_before=None: {
            "cli_invocations": 0, "cli_invocation_log": []}
        try:
            exc = self.qualify()
        finally:
            reviewer.invocation_accounting = saved
        self.assertEqual(exc.code, 1)
        entry = self.ledger()["attempts"][0]
        self.assertEqual(entry["cli_invocations"], 1)
        self.assertIn("live count applied", entry["invocation_accounting"])
        self.assertEqual(entry["invocation_reconciliation"],
                         {"probe_id": "allowed-bundle-canary",
                          "on_disk_cli_invocations": 0, "live_cli_invocations": 1})
        self.assertEqual(self.records()[0]["invocation_reconciliation"],
                         entry["invocation_reconciliation"])

    def test_f1_lost_evidence_after_a_started_invocation_is_not_a_zero_call_exit(self):
        # both persists after the interrupt fail and the working transcript
        # is gone: the exit must say a call started, not "did not start"
        s = InterruptedSession(interrupt_on=1)
        self.use_session(s)
        saved_write = canon.write_canonical_atomic
        state = {"fail": False}

        def failing_write(path, obj):
            if state["fail"] and path.endswith("leak-probe-transcript.json"):
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
                raise OSError("disk gone")
            return saved_write(path, obj)
        original_run = s.run

        def run_then_lose_disk(prompt):
            state["fail"] = True
            return original_run(prompt)
        s.run = run_then_lose_disk
        canon.write_canonical_atomic = failing_write
        try:
            exc = self.qualify()
        finally:
            canon.write_canonical_atomic = saved_write
        self.assertEqual(s.real_invocations, 1)
        self.assertNotIn("did not start an attempt", str(exc))
        self.assertIn("session reports 1 CLI invocation(s) started", str(exc))
        self.assertIn("stays reserved", str(exc))
        self.assertIn("is spent", str(self.qualify()))
        self.assertEqual(len(self.sessions), 1)

    def test_n1_reset_window_interrupt_with_lost_evidence_is_not_a_zero_call_exit(self):
        # second adversary pass, N1: probe 1 completes (one invocation);
        # probe 2 is interrupted after the session reset its per-call
        # counter to zero and before it started an invocation; the working
        # transcript is then lost. The cumulative total (1) must decide the
        # exit, not the per-call counter (0).
        s = TotalCountingSession(interrupt_on=2, reset_before_interrupt=True)
        self.use_session(s)
        saved_write = canon.write_canonical_atomic
        state = {"fail": False}

        def failing_write(path, obj):
            if state["fail"] and path.endswith("leak-probe-transcript.json"):
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
                raise OSError("disk gone")
            return saved_write(path, obj)
        s.on_interrupt = lambda: state.__setitem__("fail", True)
        canon.write_canonical_atomic = failing_write
        try:
            exc = self.qualify()
        finally:
            canon.write_canonical_atomic = saved_write
        self.assertEqual(s.total_invocations, 1)
        self.assertEqual(s.last_invocations, 0)          # the reset window
        self.assertNotIn("did not start an attempt", str(exc))
        self.assertIn("session reports 1 CLI invocation(s) started", str(exc))
        self.assertIn("is spent", str(self.qualify()))

    def test_n2_evidence_sibling_carries_the_count_when_the_handler_is_interrupted(self):
        # second adversary pass, N2: with a cumulative total available, the
        # outer handler refreshes the in-flight entry before finalizing, so
        # the durable sibling says 1, not 0, on the W1 path
        s = TotalCountingSession(interrupt_on=1)
        self.use_session(s)
        saved = reviewer.invocation_accounting
        state = {"armed": True}

        def second_interrupt(session, total_before=None):
            if state["armed"]:
                state["armed"] = False
                raise KeyboardInterrupt()
            return saved(session, total_before)
        reviewer.invocation_accounting = second_interrupt
        try:
            exc = self.qualify()
        finally:
            reviewer.invocation_accounting = saved
        self.assertEqual(exc.code, 1)
        entry = self.ledger()["attempts"][0]
        self.assertEqual(entry["cli_invocations"], 1)
        evidence = canon.load_json(os.path.join(self.q, entry["evidence_path"]))
        self.assertEqual(evidence["preflight_result"], "FAIL")
        self.assertEqual(evidence["transcripts"][0]["cli_invocations"], 1)
        self.assertIsNone(entry["invocation_reconciliation"])  # nothing to reconcile

    def test_d2_stale_per_call_counter_does_not_over_count_with_a_total(self):
        # second adversary pass, D2: an interrupt at the very top of probe 2,
        # before the per-call counter resets, copied probe 1's stale count
        # into an entry that made no invocation. The delta of the total is
        # exact: entry 2 says 0, the receipt says 1.
        s = TotalCountingSession(interrupt_on=2, stale_counter=True)
        self.use_session(s)
        exc = self.qualify()
        self.assertEqual(exc.code, 1)
        entry = self.ledger()["attempts"][0]
        self.assertEqual(entry["model_calls"], 1)
        self.assertEqual(entry["cli_invocations"], 1)
        self.assertEqual(s.total_invocations, 1)
        evidence = canon.load_json(os.path.join(self.q, entry["evidence_path"]))
        self.assertEqual([t["cli_invocations"] for t in evidence["transcripts"]], [1, 0])
        self.assertEqual(evidence["transcripts"][1]["cli_invocation_log"], [])

    def test_v1_session_reporting_a_negative_total_publishes_no_number(self):
        # third adversary pass, V1: a session whose total goes backwards
        # published "invocations -1" on a PASS. Unreachable with the real
        # class; a hostile session now gets "unavailable", not a number.
        class Backwards(ConformantSession):
            def __init__(self):
                super().__init__()
                self.total_invocations = 0

            def run(self, prompt):
                result = super().run(prompt)
                self.total_invocations = -1
                return result
        s = Backwards()
        self.use_session(s)
        exc = self.qualify()
        self.assertEqual(exc.code, 0)   # the probes themselves passed
        entry = self.ledger()["attempts"][0]
        self.assertIsNone(entry["cli_invocations"])
        self.assertIn("unavailable (session reported an invalid", entry["invocation_accounting"])
        self.assertIsNone(entry["invocation_reconciliation"])

    def test_real_isolated_session_keeps_a_cumulative_total(self):
        session = reviewer.IsolatedSession("fake", "sys", self.q, attempts=1)
        self.assertEqual(session.total_invocations, 0)
        self.assertEqual(session.last_invocations, 0)
        calls = []

        class Boom(BaseException):
            pass

        def popen(*args, **kwargs):
            calls.append(1)
            raise Boom()
        saved = reviewer.subprocess.Popen
        reviewer.subprocess.Popen = popen
        try:
            for _ in range(2):
                with self.assertRaises(Boom):
                    session.run("prompt")
        finally:
            reviewer.subprocess.Popen = saved
        self.assertEqual(session.total_invocations, 2)   # never reset
        self.assertEqual(session.last_invocations, 1)    # per call
        self.assertEqual(reviewer.invocation_accounting(session, 1)["cli_invocations"], 1)
        self.assertEqual(reviewer.invocation_accounting(session, 2)["cli_invocations"], 0)

    def test_real_isolated_session_reports_a_live_count_when_interrupted(self):
        # the real session sets last_invocations BEFORE it spawns the CLI,
        # so an interrupt mid-invocation reads as one started invocation
        session = reviewer.IsolatedSession("fake", "sys", self.q, attempts=1)

        class Boom(BaseException):
            pass

        def popen_that_is_interrupted(*args, **kwargs):
            raise Boom()
        saved = reviewer.subprocess.Popen
        reviewer.subprocess.Popen = popen_that_is_interrupted
        try:
            with self.assertRaises(Boom):
                session.run("prompt")
        finally:
            reviewer.subprocess.Popen = saved
        self.assertEqual(reviewer.invocation_accounting(session)["cli_invocations"], 1)


@unittest.skipUnless(FIXTURE_READY, "public fixture not emitted")
class NoFollowEvidencePaths(_Harness):
    """18321488 blocking finding 2. Each planted link points at an external
    regular file whose bytes must be neither read nor modified."""

    def setUp(self):
        super().setUp()
        self.outside = tempfile.mkdtemp(prefix="hi-outside-")
        self.target = os.path.join(self.outside, "victim.json")
        self.target_bytes = b'{"attempts": [], "external": true}\n'
        with open(self.target, "wb") as f:
            f.write(self.target_bytes)
        os.chmod(self.target, 0o000)  # any read or write through the link errors

    def tearDown(self):
        os.chmod(self.target, 0o644)
        shutil.rmtree(self.outside)
        super().tearDown()

    def assert_target_untouched(self):
        os.chmod(self.target, 0o644)
        with open(self.target, "rb") as f:
            self.assertEqual(f.read(), self.target_bytes)
        os.chmod(self.target, 0o000)

    def assert_refused_before_session(self, exc, *needles):
        self.assertIn("qualification refused", str(exc))
        for needle in needles:
            self.assertIn(needle, str(exc))
        self.assertEqual(self.sessions, [])
        self.assertFalse(os.path.lexists(
            os.path.join(self.q, run_reviewer_a.RESERVATIONS_DIR, HEAD + ".json")))

    def test_symlinked_ledger_is_refused_and_never_written_through(self):
        os.symlink(self.target, os.path.join(self.q, "qualification-ledger.json"))
        exc = self.qualify()
        self.assert_refused_before_session(exc, "qualification-ledger.json is a symlink")
        self.assert_target_untouched()
        self.assertTrue(os.path.islink(os.path.join(self.q, "qualification-ledger.json")))

    def test_symlinked_working_transcript_is_refused_and_never_read(self):
        os.symlink(self.target, os.path.join(self.q, "leak-probe-transcript.json"))
        exc = self.qualify()
        self.assert_refused_before_session(exc, "leak-probe-transcript.json is a symlink")
        self.assert_target_untouched()
        self.assertEqual([f for f in os.listdir(self.q) if "STALE" in f], [])

    def test_symlinked_reservations_directory_is_refused(self):
        os.symlink(self.outside, os.path.join(self.q, run_reviewer_a.RESERVATIONS_DIR))
        exc = self.qualify()
        self.assert_refused_before_session(exc, "reservations is a symlink")
        self.assertEqual(os.listdir(self.outside), ["victim.json"])

    def test_symlinked_reservation_file_is_refused(self):
        os.makedirs(os.path.join(self.q, run_reviewer_a.RESERVATIONS_DIR))
        os.symlink(self.target, os.path.join(
            self.q, run_reviewer_a.RESERVATIONS_DIR, HEAD + ".json"))
        exc = self.qualify()
        self.assertIn("qualification refused", str(exc))
        self.assertIn("is a symlink", str(exc))
        self.assertEqual(self.sessions, [])
        self.assert_target_untouched()

    def test_symlinked_qualification_root_is_refused(self):
        link = os.path.join(self.outside, "root-link")
        os.symlink(self.q, link)
        run_reviewer_a.Q_OUT = link
        exc = self.qualify()
        self.assert_refused_before_session(exc, "is a symlink, not a directory")
        self.assertEqual(os.listdir(self.q), [])

    def test_symlinked_ancestor_under_the_pass_root_is_refused(self):
        # a link planted at out-qualification/ itself, checked without
        # touching the real tree: the check walks ancestors below `root`
        root = tempfile.mkdtemp(prefix="hi-root-")
        try:
            os.symlink(self.outside, os.path.join(root, "out-qualification"))
            q_out = os.path.join(root, "out-qualification", "reviewer-a")
            problems = run_reviewer_a.check_evidence_paths(q_out, root=root)
            self.assertEqual(len(problems), 1)
            self.assertIn("out-qualification is a symlink", problems[0])
        finally:
            shutil.rmtree(root)

    def test_symlinked_stale_manifest_and_preflight_manifest_are_refused(self):
        for name in (run_reviewer_a.STALE_MANIFEST,
                     reviewer.FAILED_PREFLIGHT_MANIFEST,
                     reviewer.PASSED_PREFLIGHT_MANIFEST):
            with self.subTest(name=name):
                os.symlink(self.target, os.path.join(self.q, name))
                exc = self.qualify()
                self.assert_refused_before_session(exc, f"{name} is a symlink")
                self.assert_target_untouched()
                os.unlink(os.path.join(self.q, name))

    def test_special_file_in_the_root_is_refused(self):
        os.mkfifo(os.path.join(self.q, "qualification-ledger.json"))
        exc = self.qualify()
        self.assert_refused_before_session(exc, "is a special file")

    def test_clean_root_passes_the_gate_and_a_run_leaves_only_regular_files(self):
        self.assertEqual(run_reviewer_a.check_evidence_paths(self.q), [])
        self.assertEqual(self.qualify().code, 0)
        self.assertEqual(run_reviewer_a.check_evidence_paths(self.q), [])
        self.assertEqual([f for f in os.listdir(self.q) if f.startswith(".tmp-")], [])
        for name in os.listdir(self.q):
            path = os.path.join(self.q, name)
            if name == run_reviewer_a.RESERVATIONS_DIR:
                self.assertTrue(canon.is_real_dir(path))
            else:
                self.assertTrue(canon.is_regular(path), name)

    def test_atomic_writer_refuses_a_symlink_destination(self):
        link = os.path.join(self.q, "manifest.json")
        os.symlink(self.target, link)
        with self.assertRaises(canon.PathBoundaryError):
            canon.write_canonical_atomic(link, {"x": 1})
        self.assert_target_untouched()
        self.assertTrue(os.path.islink(link))
        self.assertEqual([f for f in os.listdir(self.q) if f.startswith(".tmp-")], [])

    def test_atomic_writer_replaces_a_regular_file_in_place(self):
        path = os.path.join(self.q, "manifest.json")
        canon.write_canonical_atomic(path, {"v": 1})
        ino = os.lstat(path).st_ino
        canon.write_canonical_atomic(path, {"v": 2})
        self.assertEqual(canon.load_json(path), {"v": 2})
        self.assertNotEqual(os.lstat(path).st_ino, ino)  # replaced, not rewritten
        self.assertEqual([f for f in os.listdir(self.q) if f.startswith(".tmp-")], [])

    def test_no_follow_reader_refuses_a_symlink(self):
        link = os.path.join(self.q, "in.json")
        os.symlink(self.target, link)
        with self.assertRaises(canon.PathBoundaryError):
            canon.read_regular_bytes(link)
        self.assert_target_untouched()

    def test_append_ledger_refuses_a_symlink_after_a_spend(self):
        # the seam itself, called directly: even if the pre-run gate were
        # bypassed, the ledger write refuses to follow a link
        os.symlink(self.target, os.path.join(self.q, "qualification-ledger.json"))
        with self.assertRaises(canon.PathBoundaryError):
            run_reviewer_a.append_ledger(self.q, {"head": HEAD})
        self.assert_target_untouched()

    def test_stash_refuses_a_symlinked_working_transcript(self):
        os.symlink(self.target, os.path.join(self.q, "leak-probe-transcript.json"))
        with self.assertRaises(canon.PathBoundaryError):
            run_reviewer_a.stash_stale_transcript(self.q, HEAD)
        self.assert_target_untouched()
        self.assertEqual([f for f in os.listdir(self.q) if "STALE" in f], [])


if __name__ == "__main__":
    unittest.main()
