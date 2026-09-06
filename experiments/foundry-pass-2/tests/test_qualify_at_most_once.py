"""At-most-once qualification (Ari, discussioncomment-18321030, two blocking
findings against 12631b6):

1. The qualify path constructed its session with IsolatedSession's default
   of three CLI attempts. Invocations were counted (12631b6) but not
   prevented; ruling 18218358 permits no second invocation.
2. Refusal consulted only qualification-ledger.json, which is the LAST
   thing written. A ledger-write failure after the model call left the
   head absent from the sole refusal source; a second call at the same
   head spent a second invocation (reproduced by Ari without a model).

Fixes held here: the qualify path builds a one-attempt session and
refuses a session that allows more; an exclusive, durable reservation
keyed by exact head is written after the deterministic input checks and
before any session exists; refusal treats the reservation as
authoritative, then the immutable attempt records, then the ledger.
Fault injection at attempt-record creation and at ledger finalization
each prove a second call at the same head is refused with zero new
sessions.

Every test writes only under temp directories. The fake `claude` binary
counts its own invocations, so "one invocation" is proved by the binary,
not by the harness's accounting.
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
try:  # `discover -s tests -t .` imports as a package; direct runs do not
    from tests.test_self_adversarial_89a56c9 import ConformantSession, _accept  # noqa: E402
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_self_adversarial_89a56c9 import ConformantSession, _accept  # noqa: E402

FIXTURE = os.environ.get("FOUNDRY_PASS2_OUT", os.path.join(PASS2, "out-fixture"))
FIXTURE_READY = os.path.isfile(os.path.join(FIXTURE, "review-input-bundle.json"))
HEAD = "e" * 40

SAVED_KEYS = ("Q_OUT", "git_head", "make_session", "schema_validator",
              "FIXTURE_OUT", "MODEL", "cli_version", "write_attempt_record",
              "append_ledger")


class _QualifyHarness(unittest.TestCase):
    """Common stubbing: temp Q_OUT, public fixture, fake head, fake CLI
    build string (CI runners have no `claude`), accepting validator."""

    def setUp(self):
        self.q = tempfile.mkdtemp(prefix="amo-")
        self.saved = {k: getattr(run_reviewer_a, k) for k in SAVED_KEYS}
        run_reviewer_a.Q_OUT = self.q
        run_reviewer_a.FIXTURE_OUT = FIXTURE
        run_reviewer_a.MODEL = "fake"
        run_reviewer_a.git_head = lambda: (HEAD, True)
        run_reviewer_a.cli_version = lambda: "fake-cli"
        run_reviewer_a.schema_validator = _accept
        os.environ["FOUNDRY_QUALIFY_RULED_MODEL"] = "fake"
        self.sessions = []
        self.attempts_seen = []
        self.reservation_at_construction = False

        def make(system_prompt, cwd, attempts=3):
            # the reservation must exist BEFORE any session is constructed
            self.reservation_at_construction = os.path.isfile(
                run_reviewer_a.reservation_path(self.q, HEAD))
            self.attempts_seen.append(attempts)
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

    def qualify(self):
        with self.assertRaises(SystemExit) as ctx:
            run_reviewer_a.qualify()
        return ctx.exception

    def assert_refused(self, exc, *needles):
        self.assertIn("qualification refused", str(exc))
        self.assertIn("is spent", str(exc))
        for needle in needles:
            self.assertIn(needle, str(exc))


@unittest.skipUnless(FIXTURE_READY, "public fixture not emitted")
class QualifySessionAllowsOneInvocation(_QualifyHarness):
    """Finding 1: the qualify path must construct a one-attempt session."""

    def test_session_is_built_with_exactly_one_attempt(self):
        self.assertEqual(self.qualify().code, 0)
        self.assertEqual(self.attempts_seen, [1])
        self.assertEqual(run_reviewer_a.QUALIFY_ATTEMPTS, 1)
        record = [f for f in os.listdir(self.q)
                  if f.startswith("qualification-attempt-")]
        self.assertEqual(len(record), 1)
        rec = canon.load_json(os.path.join(self.q, record[0]))
        self.assertEqual(rec["attempts_allowed"], 1)
        ledger = canon.load_json(os.path.join(self.q, "qualification-ledger.json"))
        self.assertEqual(ledger["attempts"][0]["attempts_allowed"], 1)
        self.assertEqual(ledger["attempts"][0]["cli_invocations"], 2)  # 2 probes, 1 each

    def test_session_allowing_retries_is_refused_before_any_call(self):
        def multi(system_prompt, cwd, attempts=3):
            s = ConformantSession()
            s.attempts = 3  # a session that ignores the argument
            self.sessions.append(s)
            return s
        run_reviewer_a.make_session = multi
        exc = self.qualify()
        self.assertIn("reports attempts=3", str(exc))
        self.assertEqual(self.sessions[0].calls, 0)
        # the head is reserved (spent by design) even though nothing ran
        self.assert_refused(self.qualify(), "reservation")
        self.assertEqual(len(self.sessions), 1)


@unittest.skipUnless(FIXTURE_READY, "public fixture not emitted")
class RealSessionMakesOneCliInvocationThenStops(unittest.TestCase):
    """Finding 1, proved by the binary: qualify() with the REAL
    make_session and a fake `claude` on PATH that always fails. The fake
    counts every invocation. A one-attempt session invokes it once, the
    probe fails, the attempt is ledgered FAIL with invocations 1, and the
    second qualify() at the same head is refused without invoking it
    again."""

    def setUp(self):
        self.q = tempfile.mkdtemp(prefix="amo-real-")
        self.bin = tempfile.mkdtemp(prefix="amo-bin-")
        self.counter = os.path.join(self.bin, "count")
        fake = os.path.join(self.bin, "claude")
        with open(fake, "w") as f:
            f.write("#!/bin/sh\n"
                    f"n=$(cat {self.counter} 2>/dev/null || echo 0); n=$((n+1)); "
                    f"echo $n > {self.counter}\n"
                    "cat >/dev/null\n"
                    "echo 'api error' >&2; exit 1\n")
        os.chmod(fake, 0o755)
        self.path = os.environ["PATH"]
        os.environ["PATH"] = self.bin + os.pathsep + self.path
        self.sleep = reviewer.time.sleep
        reviewer.time.sleep = lambda s: None
        self.saved = {k: getattr(run_reviewer_a, k) for k in SAVED_KEYS}
        run_reviewer_a.Q_OUT = self.q
        run_reviewer_a.FIXTURE_OUT = FIXTURE
        run_reviewer_a.MODEL = "fake"
        run_reviewer_a.git_head = lambda: (HEAD, True)
        run_reviewer_a.cli_version = lambda: "fake-cli"
        run_reviewer_a.schema_validator = _accept
        os.environ["FOUNDRY_QUALIFY_RULED_MODEL"] = "fake"
        # make_session is the REAL one

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(run_reviewer_a, k, v)
        os.environ["PATH"] = self.path
        os.environ.pop("FOUNDRY_QUALIFY_RULED_MODEL", None)
        reviewer.time.sleep = self.sleep
        shutil.rmtree(self.q)
        shutil.rmtree(self.bin)

    def invocations(self):
        try:
            with open(self.counter) as f:
                return int(f.read().strip())
        except FileNotFoundError:
            return 0

    def test_failed_first_invocation_is_not_retried(self):
        with self.assertRaises(SystemExit) as ctx:
            run_reviewer_a.qualify()
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(self.invocations(), 1)
        ledger = canon.load_json(os.path.join(self.q, "qualification-ledger.json"))
        self.assertEqual(len(ledger["attempts"]), 1)
        entry = ledger["attempts"][0]
        self.assertEqual(entry["result"], "FAIL")
        self.assertEqual(entry["cli_invocations"], 1)
        self.assertEqual(entry["attempts_allowed"], 1)
        evidence = canon.load_json(os.path.join(self.q, entry["evidence_path"]))
        logs = [t["cli_invocation_log"] for t in evidence["transcripts"]
                if t.get("cli_invocation_log")]
        self.assertEqual(len(logs), 1)
        self.assertEqual([e["invocation"] for e in logs[0]], [1])
        self.assertIn("after 1 attempts", evidence["failure_reason"])
        # same head again: refused before the binary is touched
        with self.assertRaises(SystemExit) as ctx2:
            run_reviewer_a.qualify()
        self.assertIn("qualification refused", str(ctx2.exception))
        self.assertEqual(self.invocations(), 1)


@unittest.skipUnless(FIXTURE_READY, "public fixture not emitted")
class ReservationIsAuthoritative(_QualifyHarness):
    """Finding 2: fault injection after the model call. Whatever fails
    later, the reserved head is refused on the next call with zero new
    sessions."""

    def test_reservation_precedes_session_construction(self):
        self.assertEqual(self.qualify().code, 0)
        self.assertTrue(self.reservation_at_construction)
        res = canon.load_json(run_reviewer_a.reservation_path(self.q, HEAD))
        self.assertEqual(res["head"], HEAD)
        self.assertEqual(res["attempts_allowed"], 1)
        self.assertEqual(res["model_id"], "fake")
        self.assertEqual(res["model_version_or_build"], "fake-cli")

    def test_attempt_record_write_failure_still_refuses_second_call(self):
        def explode(q_out, record):
            raise OSError("disk full at attempt-record creation")
        run_reviewer_a.write_attempt_record = explode
        with self.assertRaises(OSError):
            run_reviewer_a.qualify()
        self.assertEqual(len(self.sessions), 1)
        self.assertEqual(self.sessions[0].calls, 2)
        self.assertFalse(os.path.isfile(os.path.join(self.q, "qualification-ledger.json")))
        self.assertEqual([f for f in os.listdir(self.q)
                          if f.startswith("qualification-attempt-")], [])
        # second call: refused on the reservation alone
        self.assert_refused(self.qualify(), "reservation")
        self.assertEqual(len(self.sessions), 1)

    def test_ledger_write_failure_still_refuses_second_call(self):
        def explode(q_out, entry):
            raise OSError("disk full at ledger finalization")
        run_reviewer_a.append_ledger = explode
        with self.assertRaises(OSError):
            run_reviewer_a.qualify()
        self.assertEqual(len(self.sessions), 1)
        self.assertFalse(os.path.isfile(os.path.join(self.q, "qualification-ledger.json")))
        records = [f for f in os.listdir(self.q)
                   if f.startswith("qualification-attempt-")]
        self.assertEqual(len(records), 1)
        # second call: refused; both the reservation and the attempt record
        # name the head
        self.assert_refused(self.qualify(), "reservation", "1 attempt record(s)")
        self.assertEqual(len(self.sessions), 1)

    def test_attempt_record_alone_refuses_when_reservation_is_lost(self):
        run_reviewer_a.append_ledger = lambda q_out, entry: (_ for _ in ()).throw(
            OSError("ledger lost"))
        with self.assertRaises(OSError):
            run_reviewer_a.qualify()
        os.unlink(run_reviewer_a.reservation_path(self.q, HEAD))
        self.assert_refused(self.qualify(), "1 attempt record(s)")
        self.assertEqual(len(self.sessions), 1)

    def test_ledger_alone_still_refuses(self):
        self.assertEqual(self.qualify().code, 0)
        os.unlink(run_reviewer_a.reservation_path(self.q, HEAD))
        for f in os.listdir(self.q):
            if f.startswith("qualification-attempt-"):
                os.unlink(os.path.join(self.q, f))
        self.assert_refused(self.qualify(), "already has 1 ledgered attempt")
        self.assertEqual(len(self.sessions), 1)

    def test_reservation_with_no_attempt_record_is_spent(self):
        """A crash between reservation and session construction leaves a
        reservation and nothing else; the head still needs a new commit."""
        run_reviewer_a.reserve_head(self.q, HEAD, {"reserved_utc": "t"})
        self.assert_refused(self.qualify(), "reservation")
        self.assertEqual(len(self.sessions), 0)

    def test_reservation_is_exclusive(self):
        run_reviewer_a.reserve_head(self.q, HEAD, {"reserved_utc": "t"})
        with self.assertRaises(SystemExit) as ctx:
            run_reviewer_a.reserve_head(self.q, HEAD, {"reserved_utc": "t2"})
        self.assertIn("already reserved", str(ctx.exception))
        res = canon.load_json(run_reviewer_a.reservation_path(self.q, HEAD))
        self.assertEqual(res["reserved_utc"], "t")  # first holder's bytes kept

    def test_a_new_head_is_not_refused(self):
        self.assertEqual(self.qualify().code, 0)
        run_reviewer_a.git_head = lambda: ("f" * 40, True)
        self.assertEqual(self.qualify().code, 0)
        self.assertEqual(len(self.sessions), 2)
        self.assertEqual(sorted(os.listdir(os.path.join(self.q, "reservations"))),
                         [f"{'e' * 40}.json", f"{'f' * 40}.json"])


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(FIXTURE_READY, "public fixture not emitted")
class AdversaryFindingsHeldClosed(_QualifyHarness):
    """Reproductions of the seven findings from the first isolated
    adversary pass (2026-09-06) against this correction, each now held
    closed. F1 (two probe calls per qualification) is a ruling-wording
    question, not a code change; see the board post."""

    def test_f2_git_failure_is_a_refusal_not_an_empty_head(self):
        self.assertFalse(run_reviewer_a.valid_head(""))
        self.assertFalse(run_reviewer_a.valid_head("HEAD"))
        self.assertTrue(run_reviewer_a.valid_head("a" * 40))
        run_reviewer_a.git_head = lambda: ("", True)
        exc = self.qualify()
        self.assertIn("not a 40-hex commit sha", str(exc))
        self.assertEqual(self.sessions, [])
        self.assertFalse(os.path.isdir(os.path.join(self.q, "reservations")))

    def test_f2_real_git_head_refuses_outside_a_repository(self):
        saved = run_reviewer_a.PASS2
        run_reviewer_a.PASS2 = tempfile.mkdtemp(prefix="amo-norepo-")
        try:
            with self.assertRaises(SystemExit) as ctx:
                self.saved["git_head"]()  # the real one, not the stub
            self.assertIn("git could not report the head", str(ctx.exception))
        finally:
            shutil.rmtree(run_reviewer_a.PASS2)
            run_reviewer_a.PASS2 = saved

    def test_f3_non_sha_head_cannot_name_a_path(self):
        with self.assertRaises(SystemExit):
            run_reviewer_a.reservation_path(self.q, "../../pwned-head")
        run_reviewer_a.git_head = lambda: ("../../pwned-head", True)
        self.qualify()
        self.assertEqual(self.sessions, [])
        self.assertFalse(os.path.exists(os.path.join(
            os.path.dirname(os.path.dirname(self.q)), "pwned-head.json")))

    def test_f4_stale_working_transcript_is_stashed_not_reused(self):
        # head a: a real attempt that FAILs after the model call
        def exploding(output):
            raise RuntimeError("validator down")
        run_reviewer_a.schema_validator = exploding
        run_reviewer_a.git_head = lambda: ("a" * 40, True)
        self.assertEqual(self.qualify().code, 1)
        ledger_a = canon.load_json(os.path.join(self.q, "qualification-ledger.json"))
        self.assertEqual(len(ledger_a["attempts"]), 1)
        working = os.path.join(self.q, "leak-probe-transcript.json")
        self.assertTrue(os.path.isfile(working))
        with open(working, "rb") as f:
            stale_bytes = f.read()
        # head b: aborts before any model call (session construction fails)
        run_reviewer_a.git_head = lambda: ("b" * 40, True)

        def broken(system_prompt, cwd, attempts=3):
            raise RuntimeError("no session tonight")
        run_reviewer_a.make_session = broken
        exc = self.qualify()
        self.assertIn("did not start an attempt", str(exc))
        # no ledger line for head b, no attempt record for head b
        ledger_b = canon.load_json(os.path.join(self.q, "qualification-ledger.json"))
        self.assertEqual([a["head"] for a in ledger_b["attempts"]], ["a" * 40])
        records = [canon.load_json(os.path.join(self.q, f))["head"]
                   for f in os.listdir(self.q) if f.startswith("qualification-attempt-")]
        self.assertEqual(records, ["a" * 40])
        # head a's working transcript was preserved under a STALE sibling,
        # byte-identical, and the working file is gone
        stale = [f for f in os.listdir(self.q) if "-STALE-" in f]
        self.assertEqual(len(stale), 1)
        with open(os.path.join(self.q, stale[0]), "rb") as f:
            self.assertEqual(f.read(), stale_bytes)
        self.assertFalse(os.path.isfile(working))
        # head b is reserved (spent by design) and refused next time
        self.assert_refused(self.qualify(), "reservation")

    def test_f4_evidence_with_a_known_attempt_id_is_rejected(self):
        self.assertEqual(self.qualify().code, 0)
        rec = [canon.load_json(os.path.join(self.q, f)) for f in os.listdir(self.q)
               if f.startswith("qualification-attempt-")][0]
        self.assertIn(rec["attempt_id"], run_reviewer_a.known_attempt_ids(self.q))

    def test_f5_session_without_attempts_attribute_is_refused(self):
        class Bare:  # a session that never says what it allows
            model = "fake"

            def __init__(self):
                self.calls = 0

            def run(self, prompt):
                self.calls += 1
                return {"result": "{}", "session_id": "bare", "num_turns": 1}

        def bare(system_prompt, cwd, attempts=3):
            s = Bare()
            self.sessions.append(s)
            return s
        run_reviewer_a.make_session = bare
        exc = self.qualify()
        self.assertIn("reports attempts=None", str(exc))
        self.assertEqual(self.sessions[0].calls, 0)

    def test_f5_session_that_does_not_report_invocations_is_published_unverified(self):
        class Silent(ConformantSession):
            def run(self, prompt):
                out = super().run(prompt)
                del self.last_invocations
                del self.last_invocation_log
                return out

        def make(system_prompt, cwd, attempts=3):
            s = Silent()
            s.attempts = attempts
            self.sessions.append(s)
            return s
        run_reviewer_a.make_session = make
        self.assertEqual(self.qualify().code, 0)
        entry = canon.load_json(os.path.join(self.q, "qualification-ledger.json"))["attempts"][0]
        self.assertIsNone(entry["cli_invocations"])
        self.assertEqual(entry["invocation_accounting"], "unavailable")

    def test_f6_ruled_model_must_be_stated_and_must_match(self):
        os.environ.pop("FOUNDRY_QUALIFY_RULED_MODEL", None)
        exc = self.qualify()
        self.assertIn("FOUNDRY_QUALIFY_RULED_MODEL is not set", str(exc))
        os.environ["FOUNDRY_QUALIFY_RULED_MODEL"] = "claude-opus-5"
        exc = self.qualify()
        self.assertIn("names model 'claude-opus-5' but the harness would run 'fake'",
                      str(exc))
        self.assertEqual(self.sessions, [])
        self.assertFalse(os.path.isdir(os.path.join(self.q, "reservations")))
        os.environ["FOUNDRY_QUALIFY_RULED_MODEL"] = "fake"
        self.assertEqual(self.qualify().code, 0)
        res = canon.load_json(run_reviewer_a.reservation_path(self.q, HEAD))
        self.assertEqual(res["ruled_model_id"], "fake")

    def test_f7_corrupt_ledger_is_a_refusal_not_a_traceback(self):
        self.assertEqual(self.qualify().code, 0)
        with open(os.path.join(self.q, "qualification-ledger.json"), "w") as f:
            f.write('{"attempts": [{"head": "')
        exc = self.qualify()
        self.assert_refused(exc, "reservation", "ledger unreadable")
        self.assertEqual(len(self.sessions), 1)


@unittest.skipUnless(FIXTURE_READY, "public fixture not emitted")
class SecondAdversaryPassHeldClosed(_QualifyHarness):
    """Second isolated adversary pass (2026-09-06) against the F2 to F7
    fixes: N3 (ledger path not a regular file), N4 (zero-call crash lost
    its attribution when its transcript was stashed), N5 (stash trusted the
    sibling's name over its bytes and did not fsync before unlinking). N1
    (the ruled-model gate is an attestation) and N2 (attempts and
    invocation counts are session self-report) are documented limits, not
    code changes."""

    def test_n3_ledger_path_that_is_a_directory_refuses_before_any_spend(self):
        os.makedirs(os.path.join(self.q, "qualification-ledger.json"))
        exc = self.qualify()
        # since 18321531 the path-boundary gate fires first, before any
        # evidence is read; the spent-head check would refuse it too
        self.assertIn("qualification refused", str(exc))
        self.assertIn("not a regular file", str(exc))
        self.assertEqual(self.sessions, [])
        self.assertFalse(os.path.isdir(os.path.join(self.q, "reservations")))
        self.assertIn("not a regular file",
                      "; ".join(run_reviewer_a.spent_head_reasons(self.q, HEAD)))

    def test_n5_planted_collision_cannot_destroy_the_stale_transcript(self):
        working = os.path.join(self.q, "leak-probe-transcript.json")
        data = b'{"attempt_id": "x", "started_utc": "t", "transcripts": []}'
        with open(working, "wb") as f:
            f.write(data)
        digest = canon.bytes_digest(data)
        planted = os.path.join(self.q, f"leak-probe-transcript-STALE-{digest}.json")
        with open(planted, "wb") as f:
            f.write(b"")  # a 0-byte file wearing the real digest's name
        stale = run_reviewer_a.stash_stale_transcript(self.q, HEAD)
        self.assertNotEqual(stale, planted)
        self.assertTrue(stale.endswith(f"-STALE-{digest}-1.json"))
        with open(stale, "rb") as f:
            self.assertEqual(f.read(), data)
        with open(planted, "rb") as f:
            self.assertEqual(f.read(), b"")  # the planted file is left alone
        self.assertFalse(os.path.isfile(working))
        # identical bytes under the right name: reused, not duplicated
        with open(working, "wb") as f:
            f.write(data)
        self.assertEqual(run_reviewer_a.stash_stale_transcript(self.q, HEAD), stale)

    def test_n4_stash_manifest_keeps_the_zero_call_proof_and_head_context(self):
        # head a: reserved, then the harness dies with an IN-PROGRESS
        # transcript that recorded no model result (a zero-call crash)
        run_reviewer_a.reserve_head(self.q, "a" * 40, {"reserved_utc": "t"})
        working = os.path.join(self.q, "leak-probe-transcript.json")
        canon.write_canonical(working, {
            "attempt_id": "crashed-attempt", "started_utc": "t0",
            "preflight_result": "IN-PROGRESS",
            "transcripts": [{"probe": "canary", "result": None}]})
        # head b: a normal run
        self.assertEqual(self.qualify().code, 0)
        manifest = canon.load_json(os.path.join(self.q, run_reviewer_a.STALE_MANIFEST))
        self.assertEqual(len(manifest["members"]), 1)
        m = manifest["members"][0]
        self.assertEqual(m["attempt_id"], "crashed-attempt")
        self.assertEqual(m["preflight_result"], "IN-PROGRESS")
        self.assertEqual(m["model_calls_recorded"], 0)
        self.assertEqual(m["stashed_before_attempt_at_head"], HEAD)
        self.assertEqual(m["heads_reserved_at_stash_time"], ["a" * 40, HEAD])
        self.assertTrue(os.path.isfile(os.path.join(self.q, m["stale_path"])))
        self.assertEqual(canon.file_sha256(os.path.join(self.q, m["stale_path"])),
                         m["sha256"])
        # head b's own evidence is its own
        entry = canon.load_json(os.path.join(self.q, "qualification-ledger.json"))["attempts"][0]
        self.assertEqual(entry["head"], HEAD)
        self.assertNotEqual(entry["attempt_id"], "crashed-attempt")
        record = [canon.load_json(os.path.join(self.q, f)) for f in os.listdir(self.q)
                  if f.startswith("qualification-attempt-")][0]
        self.assertEqual(record["stale_transcript_stashed"], m["stale_path"])

    def test_keyboard_interrupt_in_session_construction_is_a_reported_zero_call(self):
        def interrupted(system_prompt, cwd, attempts=3):
            raise KeyboardInterrupt()
        run_reviewer_a.make_session = interrupted
        exc = self.qualify()
        self.assertIn("did not start an attempt", str(exc))
        self.assertIn("KeyboardInterrupt", str(exc))
        self.assert_refused(self.qualify(), "reservation")
