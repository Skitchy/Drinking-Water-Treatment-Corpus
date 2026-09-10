"""Identity binding under the qualify path's discipline (maintainer
authorization discussioncomment-18371886, scope from Ari in the project
room, 2026-09-09). Before this head, `identity` built its session with the
default of three CLI attempts per probe, had no reservation, no ruled-model
attestation, no ruling reference, no attempt record, could overwrite an
existing identity, and wrote the identity through the plain writer.

Held here, no model call, every test under temp directories:

1. one attempt per probe call, and a session that allows more is refused
   before any call;
2. clean exact head, ruled model, ruling reference, auxiliary-model policy,
   and path boundary all checked BEFORE a binding-specific reservation is
   written; the reservation exists before any session is constructed;
3. an immutable attempt record on success, failure, and interrupt, with
   head, ruling, reservation and evidence digests, invocation accounting,
   and observed model usage; refusal at the same head on the reservation,
   the record, or the ledger alone;
4. an existing identity (file, link, or directory) is never overwritten;
5. a stale working transcript is stashed, never attributed;
6. the identity is installed through a same-descriptor read-back: short
   writes install byte-identical bytes, a zero count refuses, a count that
   lies about length refuses at the size check, a writer that lands the
   right length with the wrong bytes refuses at the read-back, a file that
   appears between the check and the install is not overwritten;
7. the machine-recorded auxiliary-model policy: reject fails the attempt
   when any other model is observed; accept records the named model and
   still fails on an unnamed one;
8. review-time enforcement: a review at another head, a dirty tree, a
   changed harness, model, CLI build, configuration, or evidence, or an
   identity without bound fields, refuses before any session.

Mutants this module must fail on (each run before "green" was claimed):
BINDING_ATTEMPTS = 3; the identity-exists check removed; link() replaced
by replace(); the read-back comparison removed; the policy violation no
longer failing the attempt; the head comparison removed from review
enforcement; the reservation moved after session construction; the ruling
reference no longer required.
"""

import json
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
    from tests.test_qualify_harness_integrity import InterruptedSession  # noqa: E402
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_self_adversarial_89a56c9 import ConformantSession, _accept  # noqa: E402
    from test_qualify_harness_integrity import InterruptedSession  # noqa: E402

FIXTURE = os.environ.get("FOUNDRY_PASS2_OUT", os.path.join(PASS2, "out-fixture"))
FIXTURE_READY = os.path.isfile(os.path.join(FIXTURE, "review-input-bundle.json"))
HEAD = "b" * 40
RULING = "18371886"
HAIKU = "claude-haiku-4-5-20251001"
HAIKU_USAGE = {
    "fake": {"canonicalModel": "fake", "inputTokens": 2, "outputTokens": 900},
    HAIKU: {"canonicalModel": "claude-haiku-4-5", "inputTokens": 3606,
            "outputTokens": 19},
}
REVIEWER_ONLY_USAGE = {"fake": {"canonicalModel": "fake", "inputTokens": 2,
                                "outputTokens": 900}}
ABSENT = "absent"   # the CLI result carries no modelUsage field at all

SAVED_KEYS = ("git_head", "make_session", "schema_validator", "MODEL",
              "cli_version", "write_binding_record", "append_binding_ledger",
              "os_link")
ENV_KEYS = (run_reviewer_a.IDENTITY_RULED_MODEL_VAR,
            run_reviewer_a.IDENTITY_RULING_VAR,
            run_reviewer_a.AUX_MODEL_POLICY_VAR)


class BoundSession(ConformantSession):
    """ConformantSession that also exposes what the real IsolatedSession
    exposes (command, environment boundary, timeout), taken from the real
    class so review-time enforcement recomputes the same digests. `usage`
    is copied into every result as the CLI's `modelUsage` field."""

    def __init__(self, system_prompt="", usage=None):
        super().__init__()
        self._real = reviewer.IsolatedSession("fake", system_prompt, "",
                                              attempts=1)
        self.timeout = self._real.timeout
        self.usage = usage

    def command(self):
        return self._real.command()

    def environment_boundary(self):
        return self._real.environment_boundary()

    def run(self, prompt):
        out = super().run(prompt)
        usage = REVIEWER_ONLY_USAGE if self.usage is None else self.usage
        if usage != ABSENT:
            out["modelUsage"] = json.loads(json.dumps(usage))
        return out


class BoundInterruptedSession(InterruptedSession):
    def __init__(self, interrupt_on=1, exc=KeyboardInterrupt, system_prompt=""):
        super().__init__(interrupt_on, exc)
        self._real = reviewer.IsolatedSession("fake", system_prompt, "",
                                              attempts=1)
        self.timeout = self._real.timeout

    def run(self, prompt):
        out = super().run(prompt)
        out["modelUsage"] = json.loads(json.dumps(REVIEWER_ONLY_USAGE))
        return out

    def command(self):
        return self._real.command()

    def environment_boundary(self):
        return self._real.environment_boundary()


def set_binding_env(ruled="fake", ruling=RULING, policy="reject"):
    os.environ[run_reviewer_a.IDENTITY_RULED_MODEL_VAR] = ruled
    os.environ[run_reviewer_a.IDENTITY_RULING_VAR] = ruling
    os.environ[run_reviewer_a.AUX_MODEL_POLICY_VAR] = policy


def clear_binding_env():
    for key in ENV_KEYS:
        os.environ.pop(key, None)


def bind_fixture_identity(out_root, a_out, head=HEAD, usage=None):
    """Bind a real identity under `a_out` from the bundle under `out_root`
    with a conformant fake session, the stubs the binding tests use, and
    the environment restored afterwards. Returns the identity digest.
    Shared with test_reviewer_offline, whose review fixture needs a bound
    identity now that review() enforces the bound head."""
    saved = {k: getattr(run_reviewer_a, k) for k in SAVED_KEYS}
    saved_env = {k: os.environ.get(k) for k in ENV_KEYS}
    run_reviewer_a.MODEL = "fake"
    run_reviewer_a.git_head = lambda what="qualification": (head, True)
    run_reviewer_a.cli_version = lambda: "fake-cli"
    run_reviewer_a.schema_validator = _accept
    run_reviewer_a.make_session = (
        lambda system_prompt, cwd, attempts=3: _bound(system_prompt, attempts, usage))
    set_binding_env()
    try:
        with _exit() as ctx:
            run_reviewer_a.bind_identity(out_root=out_root, a_out=a_out)
        assert ctx.code == 0, ctx.code
        ledger = canon.load_json(os.path.join(a_out, run_reviewer_a.BINDING_LEDGER))
        return ledger["attempts"][-1]["identity_sha256"]
    finally:
        for k, v in saved.items():
            setattr(run_reviewer_a, k, v)
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _bound(system_prompt, attempts, usage=None):
    s = BoundSession(system_prompt, usage)
    s.attempts = attempts
    return s


class _exit:
    """assertRaises(SystemExit) without a TestCase."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            raise AssertionError("SystemExit expected")
        if not issubclass(exc_type, SystemExit):
            return False
        self.code = exc.code
        return True


class _BindHarness(unittest.TestCase):
    def setUp(self):
        self.a = tempfile.mkdtemp(prefix="bind-")
        self.saved = {k: getattr(run_reviewer_a, k) for k in SAVED_KEYS}
        self.saved_os_write = canon.os_write
        run_reviewer_a.MODEL = "fake"
        run_reviewer_a.git_head = lambda what="qualification": (HEAD, True)
        run_reviewer_a.cli_version = lambda: "fake-cli"
        run_reviewer_a.schema_validator = _accept
        set_binding_env()
        self.sessions = []
        self.attempts_seen = []
        self.reservation_at_construction = None
        self.usage = None

        def make(system_prompt, cwd, attempts=3):
            self.reservation_at_construction = os.path.isfile(
                run_reviewer_a.reservation_path(self.a, HEAD))
            self.attempts_seen.append(attempts)
            s = _bound(system_prompt, attempts, self.usage)
            self.sessions.append(s)
            return s
        run_reviewer_a.make_session = make

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(run_reviewer_a, k, v)
        canon.os_write = self.saved_os_write
        clear_binding_env()
        shutil.rmtree(self.a)

    def use_session(self, session):
        def make(system_prompt, cwd, attempts=3):
            session.attempts = attempts
            self.sessions.append(session)
            return session
        run_reviewer_a.make_session = make

    def bind(self):
        with self.assertRaises(SystemExit) as ctx:
            run_reviewer_a.bind_identity(out_root=FIXTURE, a_out=self.a)
        return ctx.exception

    def identity_path(self):
        return os.path.join(self.a, run_reviewer_a.IDENTITY_FILE)

    def records(self, head=None):
        recs = [canon.load_json(os.path.join(self.a, f))
                for f in sorted(os.listdir(self.a))
                if f.startswith(run_reviewer_a.BINDING_RECORD_PREFIX)]
        if head is not None:
            recs = [r for r in recs if r["head"] == head]
        return recs

    def ledger(self):
        return canon.load_json(os.path.join(self.a, run_reviewer_a.BINDING_LEDGER))

    def assert_refused_before_reservation(self, exc, *needles):
        self.assertIn("identity binding refused", str(exc))
        for needle in needles:
            self.assertIn(needle, str(exc))
        self.assertEqual(self.sessions, [])
        self.assertFalse(os.path.lexists(os.path.join(
            self.a, run_reviewer_a.RESERVATIONS_DIR)))
        self.assertFalse(os.path.lexists(self.identity_path()))

    def assert_spent(self, exc, *needles):
        self.assertIn("identity binding refused", str(exc))
        self.assertIn("is spent", str(exc))
        for needle in needles:
            self.assertIn(needle, str(exc))


@unittest.skipUnless(FIXTURE_READY, "public fixture not emitted")
class OneAttemptPerProbe(_BindHarness):
    def test_session_is_built_with_exactly_one_attempt_and_records_it(self):
        self.assertEqual(self.bind().code, 0)
        self.assertEqual(self.attempts_seen, [1])
        self.assertEqual(run_reviewer_a.BINDING_ATTEMPTS, 1)
        record = self.records()
        self.assertEqual(len(record), 1)
        self.assertEqual(record[0]["attempts_allowed"], 1)
        self.assertEqual(record[0]["cli_invocations"], 2)   # 2 probes, 1 each
        self.assertEqual(record[0]["model_calls"], 2)
        identity = canon.load_json(self.identity_path())
        self.assertEqual(identity["binding_attempts_allowed"], 1)
        self.assertEqual(self.ledger()["attempts"][0]["attempts_allowed"], 1)

    def test_session_allowing_retries_is_refused_before_any_call(self):
        def multi(system_prompt, cwd, attempts=3):
            s = _bound(system_prompt, 3)   # a session that ignores the argument
            self.sessions.append(s)
            return s
        run_reviewer_a.make_session = multi
        exc = self.bind()
        self.assertIn("reports attempts=3", str(exc))
        self.assertEqual(self.sessions[0].calls, 0)
        self.assertFalse(os.path.lexists(self.identity_path()))
        # the head is reserved (spent by design) even though nothing ran
        self.assert_spent(self.bind(), "reservation")
        self.assertEqual(len(self.sessions), 1)

    def test_session_with_a_bool_timeout_is_refused_before_any_call(self):
        # adversary finding 5: True is an int; the identity must not publish
        # a configuration whose timeout is a bool
        def bool_timeout(system_prompt, cwd, attempts=3):
            s = _bound(system_prompt, attempts)
            s.timeout = True
            self.sessions.append(s)
            return s
        run_reviewer_a.make_session = bool_timeout
        exc = self.bind()
        self.assertIn("does not expose its command", str(exc))
        self.assertEqual(self.sessions[0].calls, 0)
        self.assertFalse(os.path.lexists(self.identity_path()))

    def test_more_invocations_than_calls_fails_the_attempt(self):
        # adversary finding 6: counting is not enforcement; a session that
        # passed the attempts check and then reports three invocations per
        # call has broken the ruling, and the receipt says so
        class Retrying(BoundSession):
            def run(self, prompt):
                out = super().run(prompt)
                self.last_invocations = 3
                self.last_invocation_log = [{"invocation": i, "outcome": "fake"}
                                            for i in (1, 2, 3)]
                return out
        s = Retrying()
        self.use_session(s)
        self.assertEqual(self.bind().code, 1)
        rec = self.records()[0]
        self.assertEqual(rec["result"], "FAIL")
        self.assertEqual(rec["cli_invocations"], 6)
        self.assertIn("6 CLI invocation(s) for 2 probe call(s)", rec["error"])
        self.assertFalse(os.path.lexists(self.identity_path()))

    def test_non_positive_timeout_is_refused_before_any_call(self):
        for bad in (0, -1):
            with self.subTest(timeout=bad):
                def make(system_prompt, cwd, attempts=3, t=bad):
                    s = _bound(system_prompt, attempts)
                    s.timeout = t
                    self.sessions.append(s)
                    return s
                run_reviewer_a.make_session = make
                run_reviewer_a.git_head = lambda what="qualification", t=bad: (
                    ("e" if t == 0 else "f") * 40, True)
                exc = self.bind()
                self.assertIn("does not expose its command", str(exc))
                self.assertEqual(self.sessions[-1].calls, 0)

    def test_invalid_or_absent_invocation_count_does_not_bind(self):
        # pass two, F5: a session publishing garbage or nothing escapes the
        # ceiling by having no int to compare; under binding that is FAIL
        class Backwards(BoundSession):
            def __init__(self):
                super().__init__()
                self.total_invocations = 0

            def run(self, prompt):
                out = super().run(prompt)
                self.total_invocations = -1
                return out

        class Silent(BoundSession):
            def run(self, prompt):
                out = super().run(prompt)
                del self.last_invocations
                del self.last_invocation_log
                return out
        for name, session, head in (("backwards", Backwards(), "1" * 40),
                                    ("silent", Silent(), "2" * 40)):
            with self.subTest(session=name):
                run_reviewer_a.git_head = lambda what="qualification", h=head: (h, True)
                self.use_session(session)
                self.assertEqual(self.bind().code, 1)
                rec = self.records(head)[0]
                self.assertEqual(rec["result"], "FAIL")
                self.assertIsNone(rec["cli_invocations"])
                self.assertIn("invocation count unavailable", rec["error"])
                self.assertFalse(os.path.lexists(self.identity_path()))

    def test_zero_or_mismatched_invocations_per_call_do_not_bind(self):
        # Ari, review of 42bf839, blocking finding 2: exactly one CLI
        # invocation per successful probe call, and the total reconciles
        class Zero(BoundSession):
            def run(self, prompt):
                out = super().run(prompt)
                self.last_invocations = 0
                self.last_invocation_log = []
                return out

        class SecondCallZero(BoundSession):
            def run(self, prompt):
                out = super().run(prompt)
                if self.calls == 2:
                    self.last_invocations = 0
                    self.last_invocation_log = []
                return out
        class TwoThenZero(BoundSession):
            # total reconciles (2 for 2 calls) but the calls do not
            def run(self, prompt):
                out = super().run(prompt)
                if self.calls == 1:
                    self.last_invocations = 2
                    self.last_invocation_log = [{"invocation": 1, "outcome": "fake"},
                                                {"invocation": 2, "outcome": "fake"}]
                else:
                    self.last_invocations = 0
                    self.last_invocation_log = []
                return out
        for name, session, head, expect in (
                ("zero", Zero(), "3" * 40, "0 CLI invocation(s) for 2 probe call(s)"),
                ("second-zero", SecondCallZero(), "4" * 40, "per call [1, 0]"),
                ("two-then-zero", TwoThenZero(), "5" * 40, "per call [2, 0]")):
            with self.subTest(session=name):
                run_reviewer_a.git_head = lambda what="qualification", h=head: (h, True)
                self.use_session(session)
                self.assertEqual(self.bind().code, 1)
                rec = self.records(head)[0]
                self.assertEqual(rec["result"], "FAIL")
                self.assertIn(expect, rec["error"])
                self.assertFalse(os.path.lexists(self.identity_path()))

    def test_session_without_configuration_is_refused_before_any_call(self):
        def bare(system_prompt, cwd, attempts=3):
            s = ConformantSession()   # no command(), no boundary, no timeout
            s.attempts = attempts
            self.sessions.append(s)
            return s
        run_reviewer_a.make_session = bare
        exc = self.bind()
        self.assertIn("does not expose its command", str(exc))
        self.assertEqual(self.sessions[0].calls, 0)
        self.assertFalse(os.path.lexists(self.identity_path()))


@unittest.skipUnless(FIXTURE_READY, "public fixture not emitted")
class ChecksBeforeReservation(_BindHarness):
    def test_reservation_precedes_session_construction_and_is_binding_specific(self):
        self.assertEqual(self.bind().code, 0)
        self.assertTrue(self.reservation_at_construction)
        res = canon.load_json(run_reviewer_a.reservation_path(self.a, HEAD))
        self.assertEqual(res["artifact_version"],
                         "foundry-pass-2-binding-reservation/experimental-v0.1")
        self.assertEqual(res["purpose"], "identity-binding")
        self.assertEqual(res["head"], HEAD)
        self.assertEqual(res["ruling_id"], RULING)
        self.assertEqual(res["ruled_model_id"], "fake")
        self.assertEqual(res["attempts_allowed"], 1)
        self.assertEqual(res["auxiliary_model_policy"]["policy"], "reject")
        self.assertEqual(res["model_version_or_build"], "fake-cli")
        # under the binding root, not the qualification root
        self.assertTrue(run_reviewer_a.reservation_path(self.a, HEAD)
                        .startswith(self.a + os.sep))

    def test_dirty_tree_is_refused(self):
        run_reviewer_a.git_head = lambda what="qualification": (HEAD, False)
        self.assert_refused_before_reservation(self.bind(), "not clean")

    def test_non_sha_head_is_refused_in_the_binding_wording(self):
        run_reviewer_a.git_head = lambda what="qualification": ("HEAD", True)
        self.assert_refused_before_reservation(self.bind(), "not a 40-hex commit sha")
        run_reviewer_a.git_head = lambda what="qualification": ("../../pwned", True)
        self.assert_refused_before_reservation(self.bind(), "not a 40-hex commit sha")

    def test_ruled_model_must_be_stated_and_match(self):
        os.environ.pop(run_reviewer_a.IDENTITY_RULED_MODEL_VAR)
        self.assert_refused_before_reservation(
            self.bind(), run_reviewer_a.IDENTITY_RULED_MODEL_VAR + " is not set")
        os.environ[run_reviewer_a.IDENTITY_RULED_MODEL_VAR] = "claude-opus-5"
        self.assert_refused_before_reservation(
            self.bind(), "names model 'claude-opus-5' but the harness would run 'fake'")

    def test_ruling_reference_is_required_and_is_a_comment_id(self):
        for bad in ("", "abc", "123", "18371886x", "../18371886"):
            with self.subTest(ruling=bad):
                os.environ[run_reviewer_a.IDENTITY_RULING_VAR] = bad
                self.assert_refused_before_reservation(
                    self.bind(), run_reviewer_a.IDENTITY_RULING_VAR)
        os.environ[run_reviewer_a.IDENTITY_RULING_VAR] = RULING
        self.assertEqual(self.bind().code, 0)
        self.assertEqual(self.records()[0]["ruling_id"], RULING)
        self.assertEqual(canon.load_json(self.identity_path())["ruling_id"], RULING)

    def test_aux_model_policy_is_required_and_well_formed(self):
        for bad in ("", "accept", "accept:", "allow:haiku", "accept:bad model",
                    "reject:haiku"):
            with self.subTest(policy=bad):
                os.environ[run_reviewer_a.AUX_MODEL_POLICY_VAR] = bad
                self.assert_refused_before_reservation(
                    self.bind(), run_reviewer_a.AUX_MODEL_POLICY_VAR)

    def test_existing_identity_is_refused_and_never_touched(self):
        for kind in ("file", "symlink", "directory"):
            with self.subTest(kind=kind):
                path = self.identity_path()
                if kind == "file":
                    with open(path, "wb") as f:
                        f.write(b"old identity\n")
                    before = os.lstat(path)
                elif kind == "symlink":
                    os.symlink(os.path.join(self.a, "elsewhere.json"), path)
                    before = os.lstat(path)
                else:
                    os.mkdir(path)
                    before = os.lstat(path)
                exc = self.bind()
                self.assertIn("identity binding refused", str(exc))
                self.assertEqual(self.sessions, [])
                self.assertFalse(os.path.lexists(os.path.join(self.a, "reservations")))
                after = os.lstat(path)
                self.assertEqual((before.st_ino, before.st_mode, before.st_size),
                                 (after.st_ino, after.st_mode, after.st_size))
                if kind == "file":
                    with open(path, "rb") as f:
                        self.assertEqual(f.read(), b"old identity\n")
                if kind == "directory":
                    os.rmdir(path)
                else:
                    os.unlink(path)

    def test_review_artifacts_present_before_binding_are_refused(self):
        os.makedirs(os.path.join(self.a, "run-records"))
        self.assert_refused_before_reservation(
            self.bind(), "evidence path boundary", "run-records is a directory")

    def test_symlinked_working_transcript_is_refused_before_reservation(self):
        outside = tempfile.mkdtemp(prefix="bind-outside-")
        try:
            target = os.path.join(outside, "victim.json")
            with open(target, "wb") as f:
                f.write(b"{}")
            os.symlink(target, os.path.join(self.a, "leak-probe-transcript.json"))
            self.assert_refused_before_reservation(
                self.bind(), "leak-probe-transcript.json is a symlink")
        finally:
            shutil.rmtree(outside)


@unittest.skipUnless(FIXTURE_READY, "public fixture not emitted")
class AttemptRecordOnEveryOutcome(_BindHarness):
    def test_success_record_and_ledger_carry_the_bindings(self):
        self.assertEqual(self.bind().code, 0)
        rec = self.records()[0]
        self.assertEqual(rec["artifact_version"],
                         "foundry-pass-2-binding-attempt/experimental-v0.2")
        self.assertEqual(rec["result"], "PASS")
        self.assertEqual(rec["head"], HEAD)
        self.assertEqual(rec["ruling_id"], RULING)
        self.assertEqual(rec["ruled_model_id"], "fake")
        self.assertEqual(rec["invocation_accounting"], "session-reported")
        self.assertEqual(rec["auxiliary_model_policy"]["policy"], "reject")
        self.assertEqual(rec["auxiliary_model_violations"], [])
        self.assertEqual([u["probe_id"] for u in rec["observed_model_usage"]],
                         ["allowed-bundle-canary", "forbidden-access"])
        res_path = os.path.join(self.a, rec["reservation_path"])
        self.assertEqual(canon.file_sha256(res_path), rec["reservation_sha256"])
        evidence = os.path.join(self.a, rec["evidence_path"])
        self.assertIn("-PASSED-", rec["evidence_path"])
        self.assertEqual(canon.file_sha256(evidence), rec["evidence_sha256"])
        # the record is content-addressed by its own bytes
        name = [f for f in os.listdir(self.a)
                if f.startswith(run_reviewer_a.BINDING_RECORD_PREFIX)][0]
        self.assertEqual(name, f"{run_reviewer_a.BINDING_RECORD_PREFIX}"
                               f"{canon.file_sha256(os.path.join(self.a, name))}.json")
        entry = self.ledger()["attempts"][0]
        self.assertEqual(entry["record_sha256"], name[len(run_reviewer_a.BINDING_RECORD_PREFIX):-5])
        self.assertEqual(entry["identity_sha256"], canon.file_sha256(self.identity_path()))
        identity = canon.load_json(self.identity_path())
        # the record, written after the install, attests the identity's
        # exact digest; the identity names the record only by attempt id
        self.assertEqual(rec["identity_sha256"], canon.file_sha256(self.identity_path()))
        self.assertEqual(identity["binding_attempt_id"], rec["attempt_id"])
        self.assertNotIn("binding_attempt_record_sha256", identity)
        self.assertEqual(rec["phase"], "finalized")
        self.assertEqual(identity["head"], HEAD)
        self.assertEqual(identity["leak_probe_transcript_sha256"], rec["evidence_sha256"])
        self.assertEqual(identity["leak_probe_evidence_path"], rec["evidence_path"])
        self.assertTrue(identity["eligible_for_binding"])
        self.assertFalse(identity["qualification_only"])
        self.assertEqual(identity["configuration"]["timeout_s"], 900)
        self.assertNotIn("attempts", identity["configuration"])
        self.assertEqual(identity["binding_attempts_allowed"], 1)
        # the identity passes the gate's mechanical check
        from engine import gate
        expected = {k: v for k, v in run_reviewer_a.expected_identity_fields().items()
                    if k != "leak_probe_transcript_sha256"}
        self.assertEqual(gate.check_identity(identity, "reviewer_a", expected)["status"],
                         gate.PASS)

    def test_failure_after_the_model_call_is_recorded_and_binds_nothing(self):
        def exploding(output):
            raise RuntimeError("validator down")
        run_reviewer_a.schema_validator = exploding
        self.assertEqual(self.bind().code, 1)
        rec = self.records()[0]
        self.assertEqual(rec["result"], "FAIL")
        self.assertIn("validator down", rec["error"])
        self.assertEqual(rec["model_calls"], 1)
        self.assertEqual(rec["cli_invocations"], 1)
        self.assertIn("-FAILED-", rec["evidence_path"])
        self.assertFalse(os.path.lexists(self.identity_path()))
        entry = self.ledger()["attempts"][0]
        self.assertEqual(entry["result"], "FAIL")
        self.assertIsNone(entry["identity_sha256"])
        self.assert_spent(self.bind(), "reservation", "1 attempt record(s)")
        self.assertEqual(len(self.sessions), 1)

    def test_interrupt_inside_the_model_call_is_recorded_with_its_invocation(self):
        s = BoundInterruptedSession(interrupt_on=1)
        self.use_session(s)
        self.assertEqual(self.bind().code, 1)
        self.assertEqual(s.real_invocations, 1)
        rec = self.records()[0]
        self.assertEqual(rec["result"], "FAIL")
        self.assertEqual(rec["model_calls"], 0)
        self.assertEqual(rec["cli_invocations"], 1)
        self.assertIn("KeyboardInterrupt", rec["error"])
        self.assertFalse(os.path.lexists(self.identity_path()))
        self.assert_spent(self.bind(), "reservation")

    def test_interrupt_in_second_probe_keeps_the_first_call(self):
        s = BoundInterruptedSession(interrupt_on=2, exc=GeneratorExit)
        self.use_session(s)
        self.assertEqual(self.bind().code, 1)
        rec = self.records()[0]
        self.assertEqual(rec["model_calls"], 1)
        self.assertEqual(rec["cli_invocations"], 2)
        self.assertFalse(os.path.lexists(self.identity_path()))

    def test_interrupt_inside_the_record_write_still_leaves_a_record(self):
        # adversary finding 7: the record is the only artifact carrying the
        # head, ruling, digests, accounting, and usage; a second write is
        # tried with the interruption named before the signal propagates
        real = run_reviewer_a.write_binding_record
        state = {"armed": True}

        def interrupted_once(a_out, record):
            if state["armed"]:
                state["armed"] = False
                raise KeyboardInterrupt()
            return real(a_out, record)
        run_reviewer_a.write_binding_record = interrupted_once
        with self.assertRaises(KeyboardInterrupt):
            run_reviewer_a.bind_identity(out_root=FIXTURE, a_out=self.a)
        rec = self.records()
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec[0]["head"], HEAD)
        self.assertEqual(rec[0]["ruling_id"], RULING)
        self.assertEqual(rec[0]["result"], "PASS")
        self.assertIn("KeyboardInterrupt", rec[0]["record_write_interrupted"])
        # the record is the last artifact: the identity it attests exists
        self.assertTrue(canon.is_regular(self.identity_path()))
        self.assertEqual(rec[0]["identity_sha256"], canon.file_sha256(self.identity_path()))
        self.assertIn("already exists", str(self.bind()))

    def test_install_failure_is_recorded_as_fail_with_no_identity(self):
        # Ari, review of 42bf839, blocking finding 3: the record is written
        # after the install and says what happened to it
        real = self.saved_os_write
        canon.os_write = (lambda fd, view: 0
                          if b"reviewer-identity/experimental" in bytes(view[:96])
                          else real(fd, view))   # only the identity write fails
        try:
            exc = self.bind()
        finally:
            canon.os_write = self.saved_os_write
        self.assertIn("identity temporary file", str(exc))
        rec = self.records()
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec[0]["result"], "FAIL")
        self.assertEqual(rec[0]["phase"], "install")
        self.assertIn("identity not installed", rec[0]["error"])
        self.assertIsNone(rec[0]["identity_sha256"])
        self.assertEqual(rec[0]["model_calls"], 2)
        self.assertFalse(os.path.lexists(self.identity_path()))
        entry = self.ledger()["attempts"][0]
        self.assertEqual(entry["result"], "FAIL")
        self.assertIsNone(entry["identity_sha256"])
        self.assert_spent(self.bind(), "reservation", "1 attempt record(s)")

    def test_post_reservation_refusals_leave_a_record(self):
        # Ari, blocking finding 3: a refusal after the reservation is an
        # outcome; it gets the same immutable record, result REFUSED
        def multi(system_prompt, cwd, attempts=3):
            s = _bound(system_prompt, 3)
            self.sessions.append(s)
            return s
        run_reviewer_a.make_session = multi
        exc = self.bind()
        self.assertIn("reports attempts=3", str(exc))
        rec = self.records()
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec[0]["result"], "REFUSED")
        self.assertEqual(rec[0]["phase"], "session-construction")
        self.assertEqual(rec[0]["model_calls"], 0)
        self.assertIsNone(rec[0]["attempt_id"])
        self.assertEqual(rec[0]["head"], HEAD)
        self.assertEqual(rec[0]["ruling_id"], RULING)
        self.assertEqual(canon.file_sha256(os.path.join(self.a, rec[0]["reservation_path"])),
                         rec[0]["reservation_sha256"])
        self.assertEqual(self.ledger()["attempts"][0]["result"], "REFUSED")

    def test_evidence_loss_after_a_started_invocation_is_recorded_with_the_live_count(self):
        # Ari, blocking finding 3: evidence loss must still record the head,
        # ruling, reservation, accounting, and error
        s = BoundInterruptedSession(interrupt_on=1)
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
            exc = self.bind()
        finally:
            canon.write_canonical_atomic = saved_write
        self.assertIn("session reports 1 CLI invocation(s) started", str(exc))
        rec = self.records()
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec[0]["result"], "FAIL")
        self.assertEqual(rec[0]["phase"], "reconcile")
        self.assertEqual(rec[0]["cli_invocations"], 1)
        self.assertEqual(rec[0]["live_invocations_started"], 1)
        self.assertIn("evidence on disk was not available", rec[0]["invocation_accounting"])
        self.assertIn("started", rec[0]["error"])
        self.assertIsNone(rec[0]["evidence_sha256"])
        self.assertFalse(os.path.lexists(self.identity_path()))
        self.assert_spent(self.bind(), "reservation", "1 attempt record(s)")

    def test_record_write_is_durable_and_never_leaves_a_partial_named_file(self):
        # pass three, finding 3: an interrupt inside the record write cannot
        # leave a partial file under the complete record's name
        real = self.saved_os_write
        state = {"armed": True}

        def interrupt_mid_record(fd, view):
            if state["armed"] and b"binding-attempt/experimental" in bytes(view[:96]):
                state["armed"] = False
                real(fd, view[:40])
                raise KeyboardInterrupt()
            return real(fd, view)
        canon.os_write = interrupt_mid_record
        try:
            with self.assertRaises(KeyboardInterrupt):
                run_reviewer_a.bind_identity(out_root=FIXTURE, a_out=self.a)
        finally:
            canon.os_write = self.saved_os_write
        names = [f for f in os.listdir(self.a)
                 if f.startswith(run_reviewer_a.BINDING_RECORD_PREFIX)]
        self.assertEqual(len(names), 1)
        self.assertEqual(canon.file_sha256(os.path.join(self.a, names[0])),
                         names[0][len(run_reviewer_a.BINDING_RECORD_PREFIX):-5])
        self.assertIn("record_write_interrupted", canon.load_json(os.path.join(self.a, names[0])))
        self.assertEqual([f for f in os.listdir(self.a) if f.startswith(".tmp-")], [])

    def test_record_write_that_persists_then_raises_is_not_written_twice(self):
        # pass two, F7
        real = run_reviewer_a.write_binding_record

        def persist_then_interrupt(a_out, record):
            real(a_out, record)
            raise KeyboardInterrupt()
        run_reviewer_a.write_binding_record = persist_then_interrupt
        with self.assertRaises(KeyboardInterrupt):
            run_reviewer_a.bind_identity(out_root=FIXTURE, a_out=self.a)
        rec = self.records()
        self.assertEqual(len(rec), 1)
        self.assertNotIn("record_write_interrupted", rec[0])

    def test_prior_attempt_id_in_the_evidence_is_refused(self):
        # adversary finding 10: the last defence against attributing an
        # earlier attempt's evidence to this one, pinned directly
        os.makedirs(self.a, exist_ok=True)
        transcript = os.path.join(self.a, "leak-probe-transcript.json")
        canon.write_canonical(transcript, {
            "attempt_id": "seen-before", "started_utc": "t",
            "preflight_result": "PASS", "transcripts": [], "failed_probes": []})
        session = _bound("", 1)
        with self.assertRaises(SystemExit) as ctx:
            run_reviewer_a.reconcile_attempt(session, transcript, "PASS", None,
                                             {"seen-before"}, "identity binding")
        self.assertIn("previously recorded attempt_id seen-before", str(ctx.exception))
        self.assertIn("identity binding", str(ctx.exception))

    def test_record_write_failure_still_refuses_second_bind(self):
        def explode(a_out, record):
            raise OSError("disk full at attempt-record creation")
        run_reviewer_a.write_binding_record = explode
        with self.assertRaises(OSError):
            run_reviewer_a.bind_identity(out_root=FIXTURE, a_out=self.a)
        self.assertEqual(self.sessions[0].calls, 2)
        # the install precedes the record; without a record the identity is
        # installed but unattested, and review() refuses it (below); the
        # head is spent by the reservation alone
        self.assertTrue(canon.is_regular(self.identity_path()))
        self.assertEqual(self.records(), [])
        self.assertIn("already exists", str(self.bind()))
        os.unlink(self.identity_path())
        self.assert_spent(self.bind(), "reservation")
        self.assertEqual(len(self.sessions), 1)

    def test_ledger_write_failure_after_install_still_refuses_second_bind(self):
        def explode(a_out, entry):
            raise OSError("disk full at ledger finalization")
        run_reviewer_a.append_binding_ledger = explode
        with self.assertRaises(OSError):
            run_reviewer_a.bind_identity(out_root=FIXTURE, a_out=self.a)
        self.assertTrue(canon.is_regular(self.identity_path()))
        # the identity itself refuses first (never overwritten); with it
        # gone, the reservation and the record still refuse on their own
        self.assertIn("already exists", str(self.bind()))
        os.unlink(self.identity_path())
        self.assert_spent(self.bind(), "reservation", "1 attempt record(s)")
        self.assertEqual(len(self.sessions), 1)

    def test_each_durable_trace_alone_refuses(self):
        self.assertEqual(self.bind().code, 0)
        os.unlink(self.identity_path())   # otherwise the identity check fires first
        os.unlink(run_reviewer_a.reservation_path(self.a, HEAD))
        self.assert_spent(self.bind(), "1 attempt record(s)")
        for f in os.listdir(self.a):
            if f.startswith(run_reviewer_a.BINDING_RECORD_PREFIX):
                os.unlink(os.path.join(self.a, f))
        self.assert_spent(self.bind(), "already has 1 ledgered attempt")
        self.assertEqual(len(self.sessions), 1)

    def test_a_new_head_binds_into_a_fresh_root_only(self):
        self.assertEqual(self.bind().code, 0)
        run_reviewer_a.git_head = lambda what="qualification": ("c" * 40, True)
        exc = self.bind()
        self.assertIn("already exists", str(exc))   # never overwritten
        self.assertEqual(len(self.sessions), 1)

    def test_stale_working_transcript_is_stashed_not_attributed(self):
        working = os.path.join(self.a, "leak-probe-transcript.json")
        stale = {"attempt_id": "old-attempt", "started_utc": "t0",
                 "preflight_result": "FAIL", "transcripts": [{"result": {"x": 1}}]}
        canon.write_canonical(working, stale)
        with open(working, "rb") as f:
            stale_bytes = f.read()
        self.assertEqual(self.bind().code, 0)
        rec = self.records()[0]
        self.assertNotEqual(rec["attempt_id"], "old-attempt")
        self.assertTrue(rec["stale_transcript_stashed"].startswith(
            "leak-probe-transcript-STALE-"))
        with open(os.path.join(self.a, rec["stale_transcript_stashed"]), "rb") as f:
            self.assertEqual(f.read(), stale_bytes)
        manifest = canon.load_json(os.path.join(self.a, run_reviewer_a.STALE_MANIFEST))
        self.assertEqual(manifest["members"][0]["attempt_id"], "old-attempt")
        self.assertEqual(manifest["members"][0]["stashed_before_attempt_at_head"], HEAD)


@unittest.skipUnless(FIXTURE_READY, "public fixture not emitted")
class AuxiliaryModelPolicy(_BindHarness):
    def test_reject_fails_the_attempt_when_another_model_is_observed(self):
        self.usage = HAIKU_USAGE
        self.assertEqual(self.bind().code, 1)
        rec = self.records()[0]
        self.assertEqual(rec["result"], "FAIL")
        self.assertIn("auxiliary model policy violated", rec["error"])
        self.assertIn(HAIKU, rec["error"])
        self.assertEqual(rec["auxiliary_model_violations"],
                         [f"allowed-bundle-canary: {HAIKU}", f"forbidden-access: {HAIKU}"])
        self.assertEqual(rec["failed_probes"], [])   # the probes themselves passed
        self.assertEqual(rec["model_calls"], 2)
        self.assertFalse(os.path.lexists(self.identity_path()))
        self.assertEqual(self.ledger()["attempts"][0]["result"], "FAIL")
        self.assert_spent(self.bind(), "reservation")

    def test_accept_records_the_named_model_and_binds(self):
        self.usage = HAIKU_USAGE
        os.environ[run_reviewer_a.AUX_MODEL_POLICY_VAR] = f"accept:{HAIKU}"
        self.assertEqual(self.bind().code, 0)
        identity = canon.load_json(self.identity_path())
        policy = identity["auxiliary_model_policy"]
        self.assertEqual(policy["policy"], "accept")
        self.assertEqual(policy["auxiliary_model"], HAIKU)
        self.assertIn("title", policy["disclosed_role"])
        observed = identity["observed_model_usage"]
        self.assertEqual([m["model_id"] for m in observed[0]["models"]],
                         [HAIKU, "fake"])
        self.assertEqual(observed[0]["models"][0]["canonicalModel"], "claude-haiku-4-5")
        self.assertEqual(observed[0]["models"][0]["inputTokens"], 3606)
        self.assertEqual(self.records()[0]["auxiliary_model_violations"], [])

    def test_accept_names_the_id_the_cli_reports_not_an_alias(self):
        # pass two, F2: an alias in canonicalModel is the entry's own claim;
        # the ruling names the exact id the CLI reports
        self.usage = HAIKU_USAGE
        os.environ[run_reviewer_a.AUX_MODEL_POLICY_VAR] = "accept:claude-haiku-4-5"
        self.assertEqual(self.bind().code, 1)
        self.assertIn(HAIKU, self.records()[0]["error"])
        self.assertFalse(os.path.lexists(self.identity_path()))

    def test_disallowed_id_cannot_borrow_the_accepted_canonical_id(self):
        self.usage = {"evil-model": {"canonicalModel": HAIKU},
                      "fake": {"canonicalModel": "fake"}}
        os.environ[run_reviewer_a.AUX_MODEL_POLICY_VAR] = f"accept:{HAIKU}"
        self.assertEqual(self.bind().code, 1)
        self.assertIn("evil-model", self.records()[0]["error"])

    def test_accept_of_a_different_model_still_fails_on_the_observed_one(self):
        self.usage = HAIKU_USAGE
        os.environ[run_reviewer_a.AUX_MODEL_POLICY_VAR] = "accept:claude-sonnet-5"
        self.assertEqual(self.bind().code, 1)
        self.assertIn(HAIKU, self.records()[0]["error"])
        self.assertFalse(os.path.lexists(self.identity_path()))

    def test_reviewer_model_must_be_reported_by_every_call(self):
        # Ari, review of 42bf839, blocking finding 1: an accepted auxiliary
        # model is additional, never a substitute for the ruled reviewer
        self.usage = {HAIKU: {"canonicalModel": "claude-haiku-4-5", "inputTokens": 5}}
        os.environ[run_reviewer_a.AUX_MODEL_POLICY_VAR] = f"accept:{HAIKU}"
        self.assertEqual(self.bind().code, 1)
        rec = self.records()[0]
        self.assertEqual(rec["result"], "FAIL")
        self.assertIn("reviewer model fake not reported", rec["error"])
        self.assertFalse(os.path.lexists(self.identity_path()))

    def test_reviewer_model_reported_with_no_tokens_is_not_credible(self):
        # pass three, finding 4
        for usage in ({"fake": {"canonicalModel": "fake", "inputTokens": 0, "outputTokens": 0}},
                      {"fake": "not-a-dict"}, {"fake": {"canonicalModel": "fake"}}):
            with self.subTest(usage=usage):
                head = canon.bytes_digest(json.dumps(usage, sort_keys=True).encode())[:40]
                run_reviewer_a.git_head = lambda what="qualification", h=head: (h, True)
                self.usage = usage
                self.assertEqual(self.bind().code, 1)
                self.assertIn("reported with no tokens", self.records(head)[0]["error"])
                self.assertFalse(os.path.lexists(self.identity_path()))

    def test_reviewer_model_missing_on_the_second_call_only_fails(self):
        class SecondCallHaikuOnly(BoundSession):
            def run(self, prompt):
                out = super().run(prompt)
                if self.calls == 2:
                    out["modelUsage"] = {HAIKU: {"canonicalModel": "claude-haiku-4-5"}}
                return out
        os.environ[run_reviewer_a.AUX_MODEL_POLICY_VAR] = f"accept:{HAIKU}"
        self.use_session(SecondCallHaikuOnly())
        self.assertEqual(self.bind().code, 1)
        self.assertIn("forbidden-access: reviewer model fake not reported",
                      self.records()[0]["error"])

    def test_reject_with_only_the_reviewer_model_observed_binds(self):
        self.usage = {"fake": {"canonicalModel": "fake", "inputTokens": 1,
                               "outputTokens": 1}}
        self.assertEqual(self.bind().code, 0)
        self.assertEqual(self.records()[0]["observed_model_usage"][0]["models"],
                         [{"model_id": "fake", "canonicalModel": "fake",
                           "inputTokens": 1, "outputTokens": 1}])
        for call in self.records()[0]["observed_model_usage"]:
            self.assertTrue(call["model_usage_reported"])

    def test_usage_absent_from_the_result_fails_the_attempt(self):
        # adversary finding 3: a CLI that reports nothing cannot show the
        # policy was honoured; under either policy the attempt is spent,
        # recorded as FAIL with the reason, and no identity is bound
        for policy in ("reject", f"accept:{HAIKU}"):
            with self.subTest(policy=policy):
                os.environ[run_reviewer_a.AUX_MODEL_POLICY_VAR] = policy
                self.usage = ABSENT
                run_reviewer_a.git_head = lambda what="qualification", p=policy: (
                    ("c" if policy == "reject" else "d") * 40, True)
                self.assertEqual(self.bind().code, 1)
                rec = self.records(("c" if policy == "reject" else "d") * 40)[0]
                self.assertEqual(rec["result"], "FAIL")
                self.assertIn("could not be checked", rec["error"])
                for call in rec["observed_model_usage"]:
                    self.assertFalse(call["model_usage_reported"])
                    self.assertEqual(call["models"], [])
                self.assertFalse(os.path.lexists(self.identity_path()))

    def test_usage_that_is_not_a_dict_fails_the_attempt(self):
        for bad in (None, [], "haiku", {}):
            with self.subTest(usage=bad):
                self.usage = {"__raw__": bad}
                session_usage = bad

                def make(system_prompt, cwd, attempts=3, u=session_usage):
                    s = _bound(system_prompt, attempts, ABSENT)
                    real_run = s.run

                    def run(prompt):
                        out = real_run(prompt)
                        out["modelUsage"] = u
                        return out
                    s.run = run
                    self.sessions.append(s)
                    return s
                run_reviewer_a.make_session = make
                head = canon.bytes_digest(str(bad).encode())[:40]
                run_reviewer_a.git_head = lambda what="qualification", h=head: (h, True)
                self.assertEqual(self.bind().code, 1)
                self.assertIn("could not be checked", self.records(head)[0]["error"])
                self.assertFalse(os.path.lexists(self.identity_path()))

    def test_empty_usage_on_the_second_call_only_fails(self):
        class SecondCallEmpty(BoundSession):
            def run(self, prompt):
                out = super().run(prompt)
                if self.calls == 2:
                    out["modelUsage"] = {}
                return out
        self.use_session(SecondCallEmpty())
        self.assertEqual(self.bind().code, 1)
        self.assertIn("forbidden-access", self.records()[0]["error"])

    def test_disallowed_id_cannot_borrow_the_reviewer_canonical_id(self):
        # adversary finding 4: a hostile entry keyed by a disallowed id whose
        # canonicalModel names the reviewer model is still a violation
        self.usage = {HAIKU: {"canonicalModel": "fake", "inputTokens": 5},
                      "fake": {"canonicalModel": "fake"}}
        self.assertEqual(self.bind().code, 1)
        rec = self.records()[0]
        self.assertIn(HAIKU, rec["error"])
        self.assertFalse(os.path.lexists(self.identity_path()))

    def test_accept_of_the_reviewer_model_itself_is_refused(self):
        # adversary finding 11: accept:<reviewer model> rules on nothing
        for bad in ("accept:fake", "accept:reject"):
            with self.subTest(policy=bad):
                os.environ[run_reviewer_a.AUX_MODEL_POLICY_VAR] = bad
                self.assert_refused_before_reservation(
                    self.bind(), run_reviewer_a.AUX_MODEL_POLICY_VAR)

    def test_forged_policy_is_rerun_against_the_verified_usage_at_review(self):
        # pass three, finding 2: identity and record both rewritten to say
        # "reject" over a transcript that reported the accepted Haiku call
        self.usage = HAIKU_USAGE
        os.environ[run_reviewer_a.AUX_MODEL_POLICY_VAR] = f"accept:{HAIKU}"
        self.assertEqual(self.bind().code, 0)
        identity = canon.load_json(self.identity_path())
        forged_policy = dict(identity["auxiliary_model_policy"], policy="reject",
                             auxiliary_model=None, disclosed_role=None)
        identity["auxiliary_model_policy"] = forged_policy
        os.unlink(self.identity_path())
        canon.write_canonical(self.identity_path(), identity)
        new_sha = canon.file_sha256(self.identity_path())
        name = [f for f in os.listdir(self.a)
                if f.startswith(run_reviewer_a.BINDING_RECORD_PREFIX)][0]
        record = canon.load_json(os.path.join(self.a, name))
        record["auxiliary_model_policy"] = forged_policy
        record["identity_sha256"] = new_sha
        data = canon.canonical_bytes(record)
        os.unlink(os.path.join(self.a, name))
        with open(os.path.join(self.a, f"{run_reviewer_a.BINDING_RECORD_PREFIX}{canon.bytes_digest(data)}.json"), "wb") as f:
            f.write(data)
        made = []

        def factory(system_prompt, cwd):
            made.append(cwd)
            return BoundSession(system_prompt)
        with self.assertRaises(SystemExit) as ctx:
            run_reviewer_a.review(1, session_factory=factory, out_root=FIXTURE, a_out=self.a)
        self.assertIn("verified probe evidence violates the auxiliary model policy",
                      str(ctx.exception))
        self.assertEqual(made, [])

    def test_policy_record_names_its_own_limit(self):
        self.assertEqual(self.bind().code, 0)
        policy = self.records()[0]["auxiliary_model_policy"]
        self.assertIsNone(policy["prevention_configuration"])
        self.assertIn("by observation", policy["enforcement"])


class IdentityInstallReadback(unittest.TestCase):
    """install_identity_readback on its own, with the raw write seam."""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="bind-install-")
        self.path = os.path.join(self.d, run_reviewer_a.IDENTITY_FILE)
        self.obj = {"identity": "x" * 3000, "n": list(range(200))}
        self.data = canon.canonical_bytes(self.obj)
        self.saved_write = canon.os_write
        self.saved_link = run_reviewer_a.os_link

    def tearDown(self):
        canon.os_write = self.saved_write
        run_reviewer_a.os_link = self.saved_link
        shutil.rmtree(self.d)

    def leftovers(self):
        return [f for f in os.listdir(self.d) if f.startswith(".tmp-")]

    def test_installs_byte_identical_and_returns_the_digest_of_disk(self):
        digest = run_reviewer_a.install_identity_readback(self.path, self.obj)
        with open(self.path, "rb") as f:
            on_disk = f.read()
        self.assertEqual(on_disk, self.data)
        self.assertEqual(digest, canon.bytes_digest(on_disk))
        self.assertEqual(self.leftovers(), [])
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o644)

    def test_short_writes_install_byte_identical(self):
        real = self.saved_write
        canon.os_write = lambda fd, view: real(fd, view[:23])
        run_reviewer_a.install_identity_readback(self.path, self.obj)
        with open(self.path, "rb") as f:
            self.assertEqual(f.read(), self.data)
        self.assertEqual(self.leftovers(), [])

    def test_zero_count_refuses_and_installs_nothing(self):
        canon.os_write = lambda fd, view: 0
        with self.assertRaises(canon.ShortWriteError):
            run_reviewer_a.install_identity_readback(self.path, self.obj)
        self.assertFalse(os.path.lexists(self.path))
        self.assertEqual(self.leftovers(), [])

    def test_in_range_lie_is_refused_by_the_size_check(self):
        real = self.saved_write

        def lying(fd, view):
            real(fd, view[:10])
            return min(len(view), 100)   # reports more than it wrote
        canon.os_write = lying
        with self.assertRaises(canon.ShortWriteError) as ctx:
            run_reviewer_a.install_identity_readback(self.path, self.obj)
        self.assertIn("on disk for a", str(ctx.exception))
        self.assertFalse(os.path.lexists(self.path))
        self.assertEqual(self.leftovers(), [])

    def test_right_length_wrong_bytes_is_refused_by_the_readback(self):
        # G1 (adversary pass on 15462aa): a writer that lands the right
        # number of bytes with different content passes the size check;
        # only reading back from the same descriptor catches it
        real = self.saved_write

        def substituting(fd, view):
            n = len(view)
            return real(fd, bytes(b"Z" * n))
        canon.os_write = substituting
        with self.assertRaises(canon.ShortWriteError) as ctx:
            run_reviewer_a.install_identity_readback(self.path, self.obj)
        self.assertIn("read back from the same descriptor differ", str(ctx.exception))
        self.assertFalse(os.path.lexists(self.path))
        self.assertEqual(self.leftovers(), [])

    def test_existing_identity_is_refused_untouched(self):
        with open(self.path, "wb") as f:
            f.write(b"first\n")
        ino = os.lstat(self.path).st_ino
        with self.assertRaises(SystemExit) as ctx:
            run_reviewer_a.install_identity_readback(self.path, self.obj)
        self.assertIn("already exists", str(ctx.exception))
        with open(self.path, "rb") as f:
            self.assertEqual(f.read(), b"first\n")
        self.assertEqual(os.lstat(self.path).st_ino, ino)
        self.assertEqual(self.leftovers(), [])

    def test_file_appearing_between_check_and_install_is_not_overwritten(self):
        real_link = self.saved_link

        def plant_then_link(src, dst):
            with open(dst, "wb") as f:
                f.write(b"planted\n")
            return real_link(src, dst)
        run_reviewer_a.os_link = plant_then_link
        with self.assertRaises(SystemExit) as ctx:
            run_reviewer_a.install_identity_readback(self.path, self.obj)
        self.assertIn("appeared during install", str(ctx.exception))
        with open(self.path, "rb") as f:
            self.assertEqual(f.read(), b"planted\n")
        self.assertEqual(self.leftovers(), [])

    def test_link_failure_other_than_exists_is_a_refusal(self):
        # adversary finding 9: a hard-link-hostile filesystem refuses in the
        # harness's words, nothing installed, no temporary left
        def exdev(src, dst):
            raise OSError(18, "Cross-device link")
        run_reviewer_a.os_link = exdev
        with self.assertRaises(SystemExit) as ctx:
            run_reviewer_a.install_identity_readback(self.path, self.obj)
        self.assertIn("could not be installed by link", str(ctx.exception))
        self.assertFalse(os.path.lexists(self.path))
        self.assertEqual(self.leftovers(), [])

    def test_post_install_mismatch_quarantines_the_bytes(self):
        # adversary finding 8: refused and installed must not both be true
        real_link = self.saved_link

        def link_then_overwrite(src, dst):
            real_link(src, dst)
            with open(dst, "wb") as f:
                f.write(b"tampered\n")
        run_reviewer_a.os_link = link_then_overwrite
        with self.assertRaises(SystemExit) as ctx:
            run_reviewer_a.install_identity_readback(self.path, self.obj)
        self.assertIn("does not hold the verified bytes", str(ctx.exception))
        self.assertFalse(os.path.lexists(self.path))
        quarantined = [f for f in os.listdir(self.d) if "REFUSED" in f]
        self.assertEqual(len(quarantined), 1)
        self.assertEqual(self.leftovers(), [])

    def test_two_quarantines_keep_both_artifacts_and_report_truthfully(self):
        # pass two, F6: names cannot collide, and the message claims a move
        # only when one happened
        real_link = self.saved_link
        state = {"mode": "swap"}

        def hostile_link(src, dst):
            real_link(src, dst)
            if state["mode"] == "swap":
                with open(dst, "wb") as f:
                    f.write(b"tampered\n")
            else:
                os.unlink(dst)
        run_reviewer_a.os_link = hostile_link
        with self.assertRaises(SystemExit) as first:
            run_reviewer_a.install_identity_readback(self.path, self.obj)
        self.assertIn("moved to reviewer-identity-REFUSED-", str(first.exception))
        with self.assertRaises(SystemExit) as second:
            run_reviewer_a.install_identity_readback(self.path, self.obj)
        quarantined = sorted(f for f in os.listdir(self.d) if "REFUSED" in f)
        self.assertEqual(len(quarantined), 2)
        state["mode"] = "remove"
        with self.assertRaises(SystemExit) as third:
            run_reviewer_a.install_identity_readback(self.path, self.obj)
        self.assertIn("nothing was moved", str(third.exception))
        self.assertEqual(len([f for f in os.listdir(self.d) if "REFUSED" in f]), 2)
        self.assertFalse(os.path.lexists(self.path))
        self.assertEqual(self.leftovers(), [])

    def test_symlink_at_the_identity_path_is_refused_and_never_followed(self):
        target = os.path.join(self.d, "elsewhere.json")
        with open(target, "wb") as f:
            f.write(b"victim\n")
        os.symlink(target, self.path)
        with self.assertRaises(SystemExit):
            run_reviewer_a.install_identity_readback(self.path, self.obj)
        with open(target, "rb") as f:
            self.assertEqual(f.read(), b"victim\n")
        self.assertTrue(os.path.islink(self.path))


@unittest.skipUnless(FIXTURE_READY, "public fixture not emitted")
class ReviewTimeEnforcement(_BindHarness):
    """review() refuses before any session unless the tree, harness,
    model, CLI build, configuration, and evidence match the identity."""

    def setUp(self):
        super().setUp()
        self.assertEqual(self.bind().code, 0)
        self.made = []

    def review(self):
        """The enforcement claim under test is 'a matching state reaches a
        session; anything else refuses before one'. review() now runs one
        governed command over explicit shard IDs under a ruling reference
        (18376129) and always exits through SystemExit, so: None once a
        session was constructed, the refusal text otherwise."""
        def factory(system_prompt, cwd, attempts=run_reviewer_a.REVIEW_ATTEMPTS):
            self.made.append(cwd)
            s = BoundSession(system_prompt)
            s.attempts = attempts
            return s
        manifest = canon.load_json(os.path.join(FIXTURE, "shard-manifest.json"))
        os.environ[run_reviewer_a.REVIEW_RULED_MODEL_VAR] = "fake"
        os.environ[run_reviewer_a.REVIEW_RULING_VAR] = "18376129"
        try:
            run_reviewer_a.review([manifest["shards"][0]["shard_id"]],
                                  session_factory=factory,
                                  out_root=FIXTURE, a_out=self.a)
        except SystemExit as err:
            return None if self.made else str(err)
        finally:
            os.environ.pop(run_reviewer_a.REVIEW_RULED_MODEL_VAR, None)
            os.environ.pop(run_reviewer_a.REVIEW_RULING_VAR, None)
        return None

    def rewrite_identity(self, reattest=True, **changes):
        """Edit the identity on disk. The binding record attests the
        identity's exact digest, so by default the record is re-attested to
        the edited bytes (rewritten under its new content-addressed name):
        that models a forger who can write records too, and lets each deeper
        check be exercised on its own. reattest=False leaves the record as
        it was, so the digest attestation itself is what fires."""
        identity = canon.load_json(self.identity_path())
        identity.update(changes)
        os.unlink(self.identity_path())
        canon.write_canonical(self.identity_path(), identity)
        if reattest:
            new_sha = canon.file_sha256(self.identity_path())
            for name in os.listdir(self.a):
                if not name.startswith(run_reviewer_a.BINDING_RECORD_PREFIX):
                    continue
                path = os.path.join(self.a, name)
                record = canon.load_json(path)
                if record.get("attempt_id") != identity.get("binding_attempt_id"):
                    continue
                record["identity_sha256"] = new_sha
                data = canon.canonical_bytes(record)
                os.unlink(path)
                with open(os.path.join(self.a, f"{run_reviewer_a.BINDING_RECORD_PREFIX}{canon.bytes_digest(data)}.json"), "wb") as f:
                    f.write(data)

    def test_matching_state_reaches_a_session(self):
        err = self.review()
        self.assertIsNone(err, err)
        self.assertEqual(len(self.made), 1)

    def test_another_head_is_refused_before_any_session(self):
        run_reviewer_a.git_head = lambda what="qualification": ("c" * 40, True)
        err = self.review()
        self.assertIn("review refused", err)
        self.assertIn("bound at " + HEAD, err)
        self.assertEqual(self.made, [])

    def test_dirty_tree_is_refused(self):
        run_reviewer_a.git_head = lambda what="qualification": (HEAD, False)
        err = self.review()
        self.assertIn("not clean", err)
        self.assertEqual(self.made, [])

    def test_changed_harness_is_refused(self):
        self.rewrite_identity(harness_sha256="0" * 64)
        err = self.review()
        self.assertIn("engine/reviewer.py hashes to", err)
        self.assertEqual(self.made, [])

    def test_changed_model_is_refused(self):
        run_reviewer_a.MODEL = "other-model"
        err = self.review()
        self.assertIn("would run 'other-model'", err)
        self.assertEqual(self.made, [])

    def test_changed_cli_build_is_refused(self):
        run_reviewer_a.cli_version = lambda: "fake-cli-2"
        err = self.review()
        self.assertIn("CLI build is 'fake-cli-2'", err)
        self.assertEqual(self.made, [])

    def test_changed_prompt_files_are_refused(self):
        for field, name in (("system_prompt_sha256", "reviewer-system-prompt"),
                            ("task_prompt_template_sha256", "reviewer-task-template")):
            with self.subTest(field=field):
                original = canon.load_json(self.identity_path())[field]
                self.rewrite_identity(**{field: "2" * 64})
                err = self.review()
                self.assertIn(name, err)
                self.assertIn("rebind", err)
                self.assertEqual(self.made, [])
                self.rewrite_identity(**{field: original})

    def test_changed_configuration_is_refused(self):
        self.rewrite_identity(configuration_sha256="1" * 64)
        err = self.review()
        self.assertIn("session configuration differs", err)
        self.assertEqual(self.made, [])

    def test_changed_environment_boundary_is_refused(self):
        self.rewrite_identity(environment_boundary_sha256="1" * 64)
        err = self.review()
        self.assertIn("environment boundary differs", err)
        self.assertEqual(self.made, [])

    def test_altered_or_missing_evidence_is_refused(self):
        identity = canon.load_json(self.identity_path())
        evidence = os.path.join(self.a, identity["leak_probe_evidence_path"])
        with open(evidence, "ab") as f:
            f.write(b"\n")
        err = self.review()
        self.assertIn("probe evidence", err)
        self.assertEqual(self.made, [])
        os.unlink(evidence)
        self.assertIn("probe evidence", self.review())

    def test_altered_binding_record_is_refused(self):
        name = [f for f in os.listdir(self.a)
                if f.startswith(run_reviewer_a.BINDING_RECORD_PREFIX)][0]
        with open(os.path.join(self.a, name), "ab") as f:
            f.write(b"\n")
        err = self.review()
        self.assertIn("binding attempt record", err)
        self.assertEqual(self.made, [])

    def test_identity_without_bound_fields_is_refused(self):
        identity = canon.load_json(self.identity_path())
        for field in run_reviewer_a.IDENTITY_BOUND_FIELDS:
            # the older bundle and schema checks fire on these two first
            if field not in ("bindings", "output_schema_sha256"):
                identity.pop(field, None)
        os.unlink(self.identity_path())
        canon.write_canonical(self.identity_path(), identity)
        err = self.review()
        self.assertIn("lacks bound fields", err)
        self.assertIn("head", err)
        self.assertEqual(self.made, [])

    def test_identity_edited_away_from_its_record_is_refused(self):
        # adversary finding 1: every clear-text claim the identity makes is
        # held to the digest-verified binding record
        for field, value in (("ruling_id", "18000000"), ("ruled_model_id", "x"),
                             ("binding_attempt_id", "other"),
                             ("reservation_sha256", "3" * 64),
                             ("observed_model_usage", []),
                             ("auxiliary_model_policy", {"policy": "accept"}),
                             ("bindings", {"CONTRACT_SHA256": "5" * 64})):
            with self.subTest(field=field):
                original = canon.load_json(self.identity_path())[field]
                self.rewrite_identity(**{field: value})
                try:
                    err = self.review()
                    if field == "bindings":
                        self.assertIn("bundle changed since identity was bound", err)
                    elif field == "binding_attempt_id":
                        # the verified transcript names the real attempt first
                        self.assertIn("the probe evidence it names records attempt", err)
                    elif field == "observed_model_usage":
                        self.assertIn("does not match the verified probe evidence", err)
                    elif field == "auxiliary_model_policy":
                        self.assertIn("auxiliary model policy is malformed", err)
                    else:
                        self.assertIn("binding attempt record", err)
                    self.assertEqual(self.made, [])
                finally:
                    self.rewrite_identity(**{field: original})

    def test_published_configuration_must_hash_to_its_digest(self):
        identity = canon.load_json(self.identity_path())
        configuration = dict(identity["configuration"])
        configuration["command"] = ["claude", "-p", "--dangerously-skip-permissions"]
        self.rewrite_identity(configuration=configuration)
        err = self.review()
        self.assertIn("published configuration does not hash", err)
        self.assertEqual(self.made, [])
        self.rewrite_identity(configuration=identity["configuration"],
                              environment_boundary={"tools": ["Bash"]})
        err = self.review()
        self.assertIn("published environment boundary does not hash", err)

    def test_parser_and_allowlist_digests_are_enforced(self):
        for field in ("parser_sha256", "tool_allowlist_sha256", "settings_sources_sha256"):
            with self.subTest(field=field):
                original = canon.load_json(self.identity_path())[field]
                self.rewrite_identity(**{field: "4" * 64})
                err = self.review()
                self.assertIn("parser, tool allowlist, or settings", err)
                self.assertEqual(self.made, [])
                self.rewrite_identity(**{field: original})

    def test_any_edit_without_reattestation_is_refused_by_the_digest(self):
        self.rewrite_identity(reattest=False, operator_lineage="someone else")
        err = self.review()
        self.assertIn("attests identity", err)
        self.assertIn("edited or replaced", err)
        self.assertEqual(self.made, [])

    def test_missing_reservation_is_refused(self):
        # adversary finding 2
        os.unlink(run_reviewer_a.reservation_path(self.a, HEAD))
        err = self.review()
        self.assertIn("head reservation the identity names is absent", err)
        self.assertEqual(self.made, [])

    def test_ruling_reference_alone_missing_is_refused(self):
        # adversary finding 10
        identity = canon.load_json(self.identity_path())
        identity.pop("ruling_id")
        os.unlink(self.identity_path())
        canon.write_canonical(self.identity_path(), identity)
        err = self.review()
        self.assertIn("lacks bound fields ['ruling_id']", err)
        self.assertEqual(self.made, [])

    def test_non_regular_record_is_refused_in_the_harness_words(self):
        # pass three, finding 5
        for kind in ("fifo", "symlink"):
            with self.subTest(kind=kind):
                path = os.path.join(self.a, f"{run_reviewer_a.BINDING_RECORD_PREFIX}{'7' * 64}.json")
                if kind == "fifo":
                    os.mkfifo(path)
                else:
                    os.symlink(os.path.join(self.a, "nowhere.json"), path)
                err = self.review()
                self.assertIn("is not a regular file", err)
                self.assertEqual(self.made, [])
                os.unlink(path)

    def test_identity_claims_are_recomputed_from_the_verified_transcript(self):
        # pass three, finding 2: a forger who rewrites both the identity and
        # the record still loses to the transcript the digest check just
        # verified
        identity = canon.load_json(self.identity_path())
        probes = json.loads(json.dumps(identity["leak_probes"]))
        probes[0]["result"] = "FAIL-EDITED"
        self.rewrite_identity(leak_probes=probes,
                              leak_probes_sha256=canon.content_digest(probes))
        self.assertIn("leak_probes_sha256 does not match the verified probe evidence",
                      self.review())
        self.rewrite_identity(leak_probes=identity["leak_probes"],
                              leak_probes_sha256=identity["leak_probes_sha256"],
                              binding_attempt_id="00000000-0000-0000-0000-000000000000")
        self.assertIn("the probe evidence it names records attempt", self.review())
        self.rewrite_identity(binding_attempt_id=identity["binding_attempt_id"],
                              observed_model_usage=[])
        self.assertIn("observed_model_usage does not match the verified probe evidence",
                      self.review())
        self.rewrite_identity(observed_model_usage=identity["observed_model_usage"],
                              session_ids_sha256="8" * 64)
        self.assertIn("session_ids_sha256 does not match the verified probe evidence",
                      self.review())
        self.rewrite_identity(session_ids_sha256=identity["session_ids_sha256"])
        self.assertIsNone(self.review())
        self.assertEqual(len(self.made), 1)

    def test_symlinked_identity_is_refused_and_never_followed(self):
        # adversary finding 12
        elsewhere = os.path.join(self.a, "elsewhere.json")
        os.rename(self.identity_path(), elsewhere)
        os.symlink(elsewhere, self.identity_path())
        err = self.review()
        self.assertIn("not a regular file", err)
        self.assertEqual(self.made, [])

    def test_qualification_identity_is_still_refused(self):
        self.rewrite_identity(eligible_for_binding=False, qualification_only=True)
        err = self.review()
        self.assertIn("ineligible for review", err)
        self.assertEqual(self.made, [])

    def test_eligibility_keys_deleted_is_refused(self):
        # pass two, F3: absence is not eligibility
        identity = canon.load_json(self.identity_path())
        for key in ("eligible_for_binding", "qualification_only"):
            identity.pop(key)
        os.unlink(self.identity_path())
        canon.write_canonical(self.identity_path(), identity)
        self.assertIn("ineligible for review", self.review())
        self.assertEqual(self.made, [])

    def test_role_budget_probes_and_session_ids_are_held_to_the_record(self):
        # pass two, F3
        for field, value, needle in (
                ("reviewer_role", "reviewer_b", "reviewer_role does not match"),
                ("binding_attempts_allowed", 99, "binding_attempts_allowed does not match"),
                ("session_ids_sha256", "0" * 64, "session_ids_sha256 does not match"),
                ("leak_probes_sha256", "0" * 64, "leak_probes_sha256 does not match")):
            with self.subTest(field=field):
                original = canon.load_json(self.identity_path())[field]
                self.rewrite_identity(**{field: value})
                self.assertIn(needle, self.review())
                self.assertEqual(self.made, [])
                self.rewrite_identity(**{field: original})
        identity = canon.load_json(self.identity_path())
        probes = json.loads(json.dumps(identity["leak_probes"]))
        probes[1]["result"] = "FAIL"
        self.rewrite_identity(leak_probes=probes)
        self.assertIn("published leak probe records do not hash", self.review())
        self.assertEqual(self.made, [])

    def test_bindings_subset_or_unknown_key_is_refused(self):
        identity = canon.load_json(self.identity_path())
        subset = dict(identity["bindings"])
        subset.pop("SHARD_MANIFEST_SHA256")
        self.rewrite_identity(bindings=subset)
        self.assertIn("bundle changed", self.review())
        self.rewrite_identity(bindings=dict(identity["bindings"], UNKNOWN=None))
        self.assertIn("bundle changed", self.review())
        self.assertEqual(self.made, [])

    def test_identity_over_a_failed_or_forged_record_is_refused(self):
        # pass two, F4, and Ari's finding 3: the record is found by attempt
        # id, must be unique, must say PASS, and must attest this identity
        name = [f for f in os.listdir(self.a)
                if f.startswith(run_reviewer_a.BINDING_RECORD_PREFIX)][0]
        record = canon.load_json(os.path.join(self.a, name))
        # a second record for the same attempt: ambiguity is a refusal
        forged = dict(record, result="FAIL", identity_sha256=None)
        data = canon.canonical_bytes(forged)
        extra = os.path.join(self.a, f"{run_reviewer_a.BINDING_RECORD_PREFIX}{canon.bytes_digest(data)}.json")
        with open(extra, "wb") as f:
            f.write(data)
        self.assertIn("2 binding attempt record(s) name attempt", self.review())
        self.assertEqual(self.made, [])
        os.unlink(os.path.join(self.a, name))
        # only the FAIL record remains: refused as not a passed attempt
        self.assertIn("not a passed identity-binding attempt", self.review())
        os.unlink(extra)
        # a PASS record attesting a different identity digest
        forged = dict(record, identity_sha256="9" * 64)
        data = canon.canonical_bytes(forged)
        with open(os.path.join(self.a, f"{run_reviewer_a.BINDING_RECORD_PREFIX}{canon.bytes_digest(data)}.json"), "wb") as f:
            f.write(data)
        self.assertIn("attests identity 9999", self.review())
        self.assertEqual(self.made, [])


@unittest.skipUnless(FIXTURE_READY, "public fixture not emitted")
class RealBinaryMakesOneInvocationThenStops(unittest.TestCase):
    """The real make_session and a fake `claude` on PATH that always fails:
    the binary counts one invocation, the attempt is recorded FAIL with
    invocations 1, no identity exists, and the second bind at the same head
    is refused without invoking the binary again."""

    def setUp(self):
        self.a = tempfile.mkdtemp(prefix="bind-real-")
        self.bin = tempfile.mkdtemp(prefix="bind-bin-")
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
        run_reviewer_a.MODEL = "fake"
        run_reviewer_a.git_head = lambda what="qualification": (HEAD, True)
        run_reviewer_a.cli_version = lambda: "fake-cli"
        run_reviewer_a.schema_validator = _accept
        set_binding_env()

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(run_reviewer_a, k, v)
        os.environ["PATH"] = self.path
        clear_binding_env()
        reviewer.time.sleep = self.sleep
        shutil.rmtree(self.a)
        shutil.rmtree(self.bin)

    def invocations(self):
        try:
            with open(self.counter) as f:
                return int(f.read().strip())
        except FileNotFoundError:
            return 0

    def test_failed_first_invocation_is_not_retried_and_binds_nothing(self):
        with self.assertRaises(SystemExit) as ctx:
            run_reviewer_a.bind_identity(out_root=FIXTURE, a_out=self.a)
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(self.invocations(), 1)
        ledger = canon.load_json(os.path.join(self.a, run_reviewer_a.BINDING_LEDGER))
        entry = ledger["attempts"][0]
        self.assertEqual(entry["result"], "FAIL")
        self.assertEqual(entry["cli_invocations"], 1)
        self.assertEqual(entry["attempts_allowed"], 1)
        self.assertIsNone(entry["identity_sha256"])
        self.assertFalse(os.path.lexists(os.path.join(self.a, run_reviewer_a.IDENTITY_FILE)))
        with self.assertRaises(SystemExit) as ctx2:
            run_reviewer_a.bind_identity(out_root=FIXTURE, a_out=self.a)
        self.assertIn("identity binding refused", str(ctx2.exception))
        self.assertEqual(self.invocations(), 1)


if __name__ == "__main__":
    unittest.main()
