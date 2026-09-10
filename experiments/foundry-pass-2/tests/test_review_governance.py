"""Governed review under the binding path's discipline (maintainer
authorization discussioncomment-18376129; scope from Ari in the project
room, 2026-09-09, message 255). Before this head, `review N` built each
shard session with three CLI attempts, picked shards by count with no
ruling reference, wrote the shard record after the model call through the
plain writer (a crash spent a call and re-ran the shard), continued after
a failed shard, checked no per-shard model usage, shared one scratch
directory across shards, and wrote the manifest only at the end.

Held here, no model call, every test under temp directories, the identity
bound for real with a fake session:

1. selection by explicit ordered shard IDs under a ruling reference and a
   ruled-model check; duplicate, unknown, malformed, and already-claimed
   IDs and a used ruling are refused BEFORE anything is reserved;
2. ONE immutable command reservation keyed by the ruling ID, written after
   every deterministic check and before any session, binding the ordered
   shard IDs with their input digests, the identity digest, model, build,
   configuration, auxiliary policy, call ceiling, and stopping rule;
3. an immutable per-shard claim keyed by shard ID immediately before that
   shard's one call; a session allowing retries, or whose configuration
   differs from the identity's, is refused before the claim;
4. exactly one CLI invocation per shard call, the reviewer model reported
   with tokens, the bound auxiliary policy honoured, or the shard FAILs in
   phase policy with no output;
5. the output installed atomically with a same-descriptor read-back, then
   the immutable shard record written LAST attesting the output digest and
   length (or the failure phase) at every exit after the claim: validation
   failure, invocation failure, interrupt, install failure, record-write
   interruption;
6. stop on the first shard that is not DONE: every remaining shard is
   NOT_RUN in the terminal command record, unclaimed, and needs a new
   ruling; a claimed shard is never re-run;
7. the run manifest is a rebuildable index: its failure never masks the
   record, and `status` rebuilds every state from claims, records, and
   outputs alone, recomputing every digest relationship;
8. existing callers unchanged: the default evidence-path gate still refuses
   a run-records directory for binding, and reserve_head keeps its words.

Mutants this module must fail on (each run before "green" was claimed):
REVIEW_ATTEMPTS = 3; the claim moved after the call; the shard record
written before the output install; the loop continuing after a failed
shard; the duplicate-ID check removed; the already-claimed check ignoring
outputs; the read-back comparison removed; the ruled-model check removed;
`invocations != 1` loosened to `> 1`; status reading the manifest instead
of the records.
"""

import contextlib
import io
import json
import os
import re
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
    from tests.test_identity_binding import bind_fixture_identity, HEAD  # noqa: E402
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_identity_binding import bind_fixture_identity, HEAD  # noqa: E402

FIXTURE = os.environ.get("FOUNDRY_PASS2_OUT", os.path.join(PASS2, "out-fixture"))
FIXTURE_READY = os.path.isfile(os.path.join(FIXTURE, "review-input-bundle.json"))
RULING = "18376129"
HAIKU = "claude-haiku-4-5-20251001"
REVIEWER_ONLY = {"fake": {"canonicalModel": "fake", "inputTokens": 2,
                          "outputTokens": 900}}
HAIKU_ONLY = {HAIKU: {"canonicalModel": "claude-haiku-4-5", "inputTokens": 3606,
                      "outputTokens": 19}}
WITH_HAIKU = dict(REVIEWER_ONLY, **HAIKU_ONLY)
ABSENT = "absent"
SAVED_KEYS = ("git_head", "cli_version", "MODEL", "make_session",
              "write_review_record", "os_link", "write_run_record_manifest")
ENV_KEYS = (run_reviewer_a.REVIEW_RULED_MODEL_VAR, run_reviewer_a.REVIEW_RULING_VAR)


def conformant_output(prompt, verdict="accept"):
    """A complete, schema-valid output for the shard the prompt carries,
    echoing the bindings the prompt actually carries, as a real conformant
    reviewer would."""
    shard = json.loads(prompt.split(reviewer.SHARD_SEPARATOR)[1]
                       .split("--- END REVIEW SHARD ---")[0])

    def header(label):
        return re.search(label + r": `([0-9a-f]{64})`", prompt).group(1)
    dispositions = [{
        "artifact_id": r["artifact_id"],
        "record_sha256": r["record_sha256"],
        "claim_payload_sha256": r["claim_payload_sha256"],
        "normalized_support_anchor_set_sha256":
            r["normalized_support_anchor_set_sha256"],
        "verdict": verdict, "rationale": "synthetic",
        "reason_codes": [] if verdict == "accept" else ["other-material-error"],
        "proposed_correction": None} for r in shard["records"]]
    return {
        "artifact_version": "foundry-pass-2-review-output/experimental-v0.1",
        "contract_sha256": header("Contract SHA-256"),
        "review_input_bundle_sha256": header("Review-input bundle SHA-256"),
        "shard_manifest_sha256": header("Shard manifest SHA-256"),
        "reviewer_identity_sha256": header("Reviewer identity SHA-256"),
        "shard_id": shard["shard_id"],
        "dispositions": dispositions,
        "completeness": {"input_artifact_count": len(dispositions),
                         "output_disposition_count": len(dispositions),
                         "duplicate_artifact_ids": [], "missing_artifact_ids": [],
                         "unexpected_artifact_ids": []},
    }


class GovernedShardSession:
    """A one-attempt session shaped like the real IsolatedSession (command,
    environment boundary, timeout, cumulative and per-call invocation
    accounting) that answers a real shard prompt conformantly. `usage` is
    copied into every result as the CLI's modelUsage; `response` overrides
    the raw text; `invocations` is what each call reports having run."""
    model = "fake"

    def __init__(self, system_prompt="", usage=None, response=None,
                 invocations=1, verdict="accept"):
        self._real = reviewer.IsolatedSession("fake", system_prompt, "",
                                              attempts=1)
        self.attempts = 1
        self.timeout = self._real.timeout
        self.usage = usage
        self.response = response
        self.invocations = invocations
        self.verdict = verdict
        self.calls = 0
        self.last_invocations = 0
        self.last_invocation_log = []
        self.total_invocations = 0
        self.prompts = []

    def command(self):
        return self._real.command()

    def environment_boundary(self):
        return self._real.environment_boundary()

    def account(self):
        self.calls += 1
        self.total_invocations += self.invocations
        self.last_invocations = self.invocations
        self.last_invocation_log = [{"invocation": i + 1, "outcome": "fake"}
                                    for i in range(self.invocations)]

    def run(self, prompt):
        self.account()
        self.prompts.append(prompt)
        text = (self.response if self.response is not None
                else json.dumps(conformant_output(prompt, self.verdict)))
        out = {"result": text, "session_id": f"fake-session-{self.calls}",
               "num_turns": 1}
        usage = REVIEWER_ONLY if self.usage is None else self.usage
        if usage != ABSENT:
            out["modelUsage"] = json.loads(json.dumps(usage))
        return out


class RaisingSession(GovernedShardSession):
    """Starts its one invocation (the accounting proves it), then raises."""

    def __init__(self, exc, **kw):
        super().__init__(**kw)
        self.exc = exc

    def run(self, prompt):
        self.account()
        self.prompts.append(prompt)
        raise self.exc


class NoAccountingSession(GovernedShardSession):
    """A session that never says what it ran."""

    def account(self):
        self.calls += 1
        for name in ("last_invocations", "last_invocation_log",
                     "total_invocations"):
            if hasattr(self, name):
                delattr(self, name)


@unittest.skipUnless(FIXTURE_READY, "public fixture not emitted")
class _ReviewHarness(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="review-gov-")
        self.out = os.path.join(self.root, "out")
        shutil.copytree(FIXTURE, self.out)
        self.a = os.path.join(self.root, "reviewer-a")
        os.makedirs(self.a)
        self.saved = {k: getattr(run_reviewer_a, k) for k in SAVED_KEYS}
        self.saved_os_write = canon.os_write
        self.identity_sha = bind_fixture_identity(self.out, self.a)
        run_reviewer_a.MODEL = "fake"
        run_reviewer_a.git_head = lambda what="qualification": (HEAD, True)
        run_reviewer_a.cli_version = lambda: "fake-cli"
        os.environ[run_reviewer_a.REVIEW_RULED_MODEL_VAR] = "fake"
        os.environ[run_reviewer_a.REVIEW_RULING_VAR] = RULING
        manifest = canon.load_json(os.path.join(self.out, "shard-manifest.json"))
        self.members = manifest["shards"]
        self.ids = [m["shard_id"] for m in self.members[:2]]
        self.made = []       # (cwd, attempts) per constructed session
        self.sessions = []
        self.usage = None
        self.queue = []      # sessions to hand out in order, else a default

        def make(system_prompt, cwd, attempts=3):
            self.made.append((cwd, attempts))
            s = (self.queue.pop(0) if self.queue
                 else GovernedShardSession(system_prompt, usage=self.usage))
            s.attempts = attempts
            self.sessions.append(s)
            return s
        self.factory = make

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(run_reviewer_a, k, v)
        canon.os_write = self.saved_os_write
        for k in ENV_KEYS:
            os.environ.pop(k, None)
        shutil.rmtree(self.root)

    # -- the command -----------------------------------------------------
    def review(self, ids=None, factory=None):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with self.assertRaises(SystemExit) as ctx:
                run_reviewer_a.review(self.ids if ids is None else ids,
                                      session_factory=factory or self.factory,
                                      out_root=self.out, a_out=self.a)
        self.stdout = buf.getvalue()
        return ctx.exception.code

    def review_raises(self, exc_type, ids=None, factory=None):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with self.assertRaises(exc_type):
                run_reviewer_a.review(self.ids if ids is None else ids,
                                      session_factory=factory or self.factory,
                                      out_root=self.out, a_out=self.a)
        self.stdout = buf.getvalue()

    # -- the artifacts ---------------------------------------------------
    def path(self, *parts):
        return os.path.join(self.a, *parts)

    def reservation(self, ruling=RULING):
        p = self.path(run_reviewer_a.RESERVATIONS_DIR,
                      f"{run_reviewer_a.REVIEW_RESERVATION_PREFIX}{ruling}.json")
        return canon.load_json(p) if os.path.lexists(p) else None

    def claim(self, sid):
        p = self.path(run_reviewer_a.CLAIMS_DIR, f"{sid}.json")
        return canon.load_json(p) if os.path.lexists(p) else None

    def records(self, sid):
        d = self.path(run_reviewer_a.RUN_RECORDS_DIR)
        if not os.path.isdir(d):
            return []
        out = []
        for name in sorted(os.listdir(d)):
            if name.startswith(sid + ".") and name.endswith(".json"):
                data = canon.read_regular_bytes(os.path.join(d, name))
                out.append((name[len(sid) + 1:-5], canon.bytes_digest(data),
                            json.loads(data)))
        return out

    def record(self, sid):
        recs = self.records(sid)
        self.assertEqual(len(recs), 1, recs)
        name_sha, sha, rec = recs[0]
        self.assertEqual(name_sha, sha, "record does not hash to its name")
        return rec

    def output_bytes(self, sid):
        p = self.path(run_reviewer_a.OUTPUTS_DIR, f"{sid}.json")
        return canon.read_regular_bytes(p) if os.path.lexists(p) else None

    def command_records(self):
        d = self.path(run_reviewer_a.COMMAND_RECORDS_DIR)
        if not os.path.isdir(d):
            return []
        out = []
        for name in sorted(os.listdir(d)):
            data = canon.read_regular_bytes(os.path.join(d, name))
            out.append((name, canon.bytes_digest(data), json.loads(data)))
        return out

    def command_record(self):
        recs = self.command_records()
        self.assertEqual(len(recs), 1, [r[0] for r in recs])
        name, sha, rec = recs[0]
        self.assertTrue(name.endswith(sha + ".json"), name)
        return rec

    def ledger(self):
        p = self.path(run_reviewer_a.REVIEW_LEDGER)
        return canon.load_json(p)["attempts"] if os.path.lexists(p) else []

    def manifest_kinds(self):
        p = self.path("run-record-manifest.json")
        return sorted({m["kind"] for m in canon.load_json(p)["members"]})

    def states(self):
        return run_reviewer_a.shard_states(self.out, self.a)

    def assert_nothing_reserved(self):
        self.assertIsNone(self.reservation())
        self.assertFalse(os.path.lexists(self.path(run_reviewer_a.CLAIMS_DIR)))
        self.assertFalse(os.path.lexists(self.path(run_reviewer_a.COMMAND_RECORDS_DIR)))
        self.assertEqual(self.made, [])

    def assert_not_run(self, sid):
        self.assertIsNone(self.claim(sid))
        self.assertEqual(self.records(sid), [])
        self.assertIsNone(self.output_bytes(sid))

    def _rebind_after_bundle_edit(self):
        shutil.rmtree(self.a)
        os.makedirs(self.a)
        self.identity_sha = bind_fixture_identity(self.out, self.a)
        run_reviewer_a.MODEL = "fake"
        run_reviewer_a.git_head = lambda what="qualification": (HEAD, True)
        run_reviewer_a.cli_version = lambda: "fake-cli"

    def _rewrite_manifest(self, shards):
        """Rewrite shard-manifest.json AND the bundle's declaration of its
        digest, so the edited manifest is the bound one; the identity is
        then rebound against the edited bundle."""
        manifest_path = os.path.join(self.out, "shard-manifest.json")
        canon.write_canonical(manifest_path, {"shards": shards})
        bundle_path = os.path.join(self.out, "review-input-bundle.json")
        bundle = canon.load_json(bundle_path)
        bundle["shard_manifest"]["sha256"] = canon.file_sha256(manifest_path)
        canon.write_canonical(bundle_path, bundle)
        self._rebind_after_bundle_edit()


class RefusedBeforeReservation(_ReviewHarness):
    def test_missing_ruling_reference(self):
        os.environ.pop(run_reviewer_a.REVIEW_RULING_VAR)
        err = self.review()
        self.assertIn(run_reviewer_a.REVIEW_RULING_VAR, str(err))
        self.assert_nothing_reserved()

    def test_malformed_ruling_reference(self):
        os.environ[run_reviewer_a.REVIEW_RULING_VAR] = "abc"
        self.assertIn("not a discussion comment ID", str(self.review()))
        self.assert_nothing_reserved()

    def test_missing_or_mismatched_ruled_model(self):
        os.environ.pop(run_reviewer_a.REVIEW_RULED_MODEL_VAR)
        self.assertIn(run_reviewer_a.REVIEW_RULED_MODEL_VAR, str(self.review()))
        os.environ[run_reviewer_a.REVIEW_RULED_MODEL_VAR] = "other"
        err = str(self.review())
        self.assertIn("the ruling names model 'other'", err)
        self.assert_nothing_reserved()

    def test_selection_by_count_is_refused(self):
        self.assertIn("selection by count", str(self.review(ids=1)))
        self.assertIn("non-empty list", str(self.review(ids=[])))
        self.assertIn("non-empty list", str(self.review(ids="shard-141.130")))
        self.assert_nothing_reserved()

    def test_duplicate_unknown_and_malformed_ids(self):
        sid = self.ids[0]
        self.assertIn("named more than once", str(self.review(ids=[sid, sid])))
        self.assertIn("not in the bound manifest",
                      str(self.review(ids=[sid, "shard-999.999"])))
        self.assertIn("is not a shard ID", str(self.review(ids=[sid, "../x"])))
        self.assertIn("is not a shard ID", str(self.review(ids=[sid, 7])))
        self.assert_nothing_reserved()

    def test_already_claimed_recorded_or_installed_ids(self):
        sid = self.ids[1]
        record_sha = canon.bytes_digest(canon.canonical_bytes({"shard_id": sid}))
        for sub, name in ((run_reviewer_a.CLAIMS_DIR, f"{sid}.json"),
                          (run_reviewer_a.RUN_RECORDS_DIR, f"{sid}.{record_sha}.json"),
                          (run_reviewer_a.OUTPUTS_DIR, f"{sid}.json")):
            os.makedirs(self.path(sub))
            canon.write_canonical(self.path(sub, name), {"shard_id": sid})
            err = str(self.review())
            self.assertIn("already claimed, recorded, or installed", err)
            self.assertIn(sid, err)
            self.assertIsNone(self.reservation())
            self.assertEqual(self.made, [])
            shutil.rmtree(self.path(sub))

    def test_used_ruling_is_refused(self):
        # a reservation with no terminal record is an unfinalized command:
        # refused before anything, whichever ruling the new command names
        os.makedirs(self.path(run_reviewer_a.RESERVATIONS_DIR), exist_ok=True)
        canon.write_canonical(self.path(
            run_reviewer_a.RESERVATIONS_DIR,
            f"{run_reviewer_a.REVIEW_RESERVATION_PREFIX}{RULING}.json"),
            {"command_attempt_id": "planted"})
        err = str(self.review())
        self.assertIn("not finalized", err)
        self.assertIn("no terminal command record", err)
        self.assertEqual(self.made, [])
        os.environ[run_reviewer_a.REVIEW_RULING_VAR] = "18376200"
        self.assertIn("not finalized", str(self.review()))
        self.assertEqual(self.made, [])
        self.assertIsNone(self.reservation("18376200"))

    def test_planted_link_in_an_evidence_directory_is_refused(self):
        os.makedirs(self.path(run_reviewer_a.CLAIMS_DIR))
        os.symlink(os.path.join(self.root, "elsewhere"),
                   self.path(run_reviewer_a.CLAIMS_DIR, "planted.json"))
        err = str(self.review())
        self.assertIn("evidence path boundary", err)
        self.assertIn("planted.json is a symlink", err)
        self.assertIsNone(self.reservation())
        os.unlink(self.path(run_reviewer_a.CLAIMS_DIR, "planted.json"))
        os.rmdir(self.path(run_reviewer_a.CLAIMS_DIR))
        os.symlink(os.path.join(self.root, "elsewhere"),
                   self.path(run_reviewer_a.OUTPUTS_DIR))
        err = str(self.review())
        self.assertIn("outputs is a symlink", err)
        self.assert_nothing_reserved()

    def test_corrupt_selected_shard_aborts_before_reservation(self):
        member = self.members[1]
        shard_path = os.path.join(self.out, member["path"])
        shard = canon.load_json(shard_path)
        shard["records"][0]["record_sha256"] = "0" * 64
        canon.write_canonical(shard_path, shard)
        member["sha256"] = canon.file_sha256(shard_path)
        self._rewrite_manifest(self.members)
        err = str(self.review())
        self.assertIn("aborted before any session", err)
        self.assertIn("record-identity-failed", err)
        self.assert_nothing_reserved()

    def test_manifest_not_hashing_to_the_bound_digest_is_refused(self):
        # adversary finding 1: the bundle's self-declared digest was trusted
        # and the manifest on disk never hashed; an injected row named a
        # shard the ruling never named and the same bytes were reviewed twice
        manifest_path = os.path.join(self.out, "shard-manifest.json")
        shards = [dict(m) for m in self.members]
        shards.append(dict(self.members[0], shard_id="shard-999.1"))
        canon.write_canonical(manifest_path, {"shards": shards})
        err = str(self.review(ids=["shard-999.1"]))
        self.assertIn("not the bound manifest", err)
        self.assert_nothing_reserved()
        # the same row bound for real is a duplicate of the input bytes under
        # another ID; the harness cannot know that, so the maintainer's
        # ruling over the bound manifest is the authority; the row is at
        # least refused when it names a path outside the bundle root
        shards[-1] = dict(self.members[0], shard_id="shard-999.2",
                          path="../outside.json")
        self._rewrite_manifest(shards)
        err = str(self.review(ids=["shard-999.2"]))
        self.assertIn("outside the bundle root", err)
        self.assert_nothing_reserved()

    def test_missing_shard_file_is_a_refusal_not_a_traceback(self):
        shards = [dict(m) for m in self.members]
        shards[1] = dict(shards[1], path="shards/does-not-exist.json")
        self._rewrite_manifest(shards)
        err = str(self.review())
        self.assertIn("absent or not a regular file", err)
        self.assert_nothing_reserved()

    def test_store_holding_what_the_harness_did_not_write_is_refused(self):
        # adversary finding 7: a record named <shard_id>.json parsed as a
        # different ID; now any record not shaped <id>.<sha>.json, or whose
        # content names another shard, refuses the command
        d = self.path(run_reviewer_a.RUN_RECORDS_DIR)
        os.makedirs(d)
        canon.write_canonical(os.path.join(d, f"{self.ids[0]}.json"),
                              {"shard_id": self.ids[0], "result": "DONE"})
        spent = run_reviewer_a.claimed_shard_ids(self.a)
        self.assertIn(self.ids[0], spent)
        err = str(self.review(ids=[self.members[2]["shard_id"]]))
        self.assertIn("not a content-addressed record name", err)
        self.assert_nothing_reserved()
        os.unlink(os.path.join(d, f"{self.ids[0]}.json"))
        # a name whose digest part is not the bytes' digest (second pass,
        # note 8: the shape check is the hash, not a regex)
        canon.write_canonical(os.path.join(d, f"{self.ids[0]}.{'0' * 64}.json"),
                              {"shard_id": self.ids[1]})
        self.assertEqual(run_reviewer_a.claimed_shard_ids(self.a) & set(self.ids),
                         set(self.ids))
        err = str(self.review(ids=[self.members[2]["shard_id"]]))
        self.assertIn("does not hash to its name", err)
        os.unlink(os.path.join(d, f"{self.ids[0]}.{'0' * 64}.json"))
        # a correctly hashed name whose content names another shard
        wrong = canon.bytes_digest(canon.canonical_bytes({"shard_id": self.ids[1]}))
        canon.write_canonical(os.path.join(d, f"{self.ids[0]}.{wrong}.json"),
                              {"shard_id": self.ids[1]})
        err = str(self.review(ids=[self.members[2]["shard_id"]]))
        self.assertIn("content names", err)
        os.unlink(os.path.join(d, f"{self.ids[0]}.{wrong}.json"))
        with open(self.path(run_reviewer_a.OUTPUTS_DIR + "-x"), "w") as f:
            f.write("x")
        os.unlink(self.path(run_reviewer_a.OUTPUTS_DIR + "-x"))
        os.makedirs(self.path(run_reviewer_a.OUTPUTS_DIR))
        with open(self.path(run_reviewer_a.OUTPUTS_DIR, ".tmp-output-crash.json"), "w") as f:
            f.write("{}")
        err = str(self.review(ids=[self.members[2]["shard_id"]]))
        self.assertIn("leftover temporary file", err)
        self.assert_nothing_reserved()

    def test_enforcement_precedes_the_ruling_checks(self):
        os.environ.pop(run_reviewer_a.REVIEW_RULING_VAR)
        run_reviewer_a.git_head = lambda what="qualification": ("c" * 40, True)
        err = str(self.review())
        self.assertIn("bound at " + HEAD, err)
        self.assert_nothing_reserved()


class TwoShardsDone(_ReviewHarness):
    def test_happy_path_artifacts(self):
        self.assertEqual(self.review(), 0, self.stdout)
        # one fresh one-attempt session per shard, each scratch dir its own
        # and removed afterwards
        self.assertEqual([a for _, a in self.made], [1, 1])
        cwds = [c for c, _ in self.made]
        self.assertEqual(len(set(cwds)), 2)
        self.assertFalse(any(os.path.exists(c) for c in cwds))
        # the reservation binds what the ruling names
        res = self.reservation()
        self.assertEqual([s["shard_id"] for s in res["shards"]], self.ids)
        self.assertEqual([s["input_sha256"] for s in res["shards"]],
                         [m["sha256"] for m in self.members[:2]])
        self.assertEqual(res["identity_sha256"], self.identity_sha)
        self.assertEqual((res["ruling_id"], res["head"], res["model_id"],
                          res["model_version_or_build"], res["call_ceiling"],
                          res["attempts_allowed"]),
                         (RULING, HEAD, "fake", "fake-cli", 2, 1))
        self.assertIn("never re-run", res["stopping_rule"])
        command_id = res["command_attempt_id"]
        for sid, session in zip(self.ids, self.sessions):
            claim = self.claim(sid)
            self.assertEqual((claim["command_attempt_id"], claim["shard_id"],
                              claim["identity_sha256"]),
                             (command_id, sid, self.identity_sha))
            rec = self.record(sid)
            self.assertEqual(rec["result"], "DONE")
            self.assertEqual(rec["phase"], "finalized")
            self.assertEqual(rec["command_attempt_id"], command_id)
            self.assertEqual(rec["cli_invocations"], 1)
            self.assertEqual(rec["model_calls"], 1)
            self.assertEqual(rec["verdict"], "fixed")
            self.assertEqual(rec["session_id"], "fake-session-1")
            self.assertTrue(rec["observed_model_usage"][0]["model_usage_reported"])
            self.assertEqual(rec["auxiliary_model_violations"], [])
            self.assertEqual(rec["claim_path"], f"claims/{sid}.json")
            self.assertEqual(rec["claim_sha256"], canon.file_sha256(
                self.path(run_reviewer_a.CLAIMS_DIR, f"{sid}.json")))
            expected = canon.canonical_bytes(conformant_output(session.prompts[0]))
            out = self.output_bytes(sid)
            self.assertEqual(out, expected)
            self.assertEqual(rec["output_sha256"], canon.bytes_digest(out))
            self.assertEqual(rec["output_byte_length"], len(out))
            self.assertEqual(rec["raw_response_sha256"],
                             canon.content_digest(session.prompts and
                                                  json.dumps(conformant_output(session.prompts[0]))))
            self.assertIn(self.identity_sha, session.prompts[0])
        cmd = self.command_record()
        self.assertEqual(cmd["result"], "PASS")
        self.assertEqual([s["result"] for s in cmd["shards"]], ["DONE", "DONE"])
        self.assertEqual(cmd["model_calls"], 2)
        self.assertEqual(cmd["cli_invocations"], 2)
        self.assertEqual([s["record_sha256"] for s in cmd["shards"]],
                         [self.records(s)[0][1] for s in self.ids])
        ledger = self.ledger()
        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger[0]["result"], "PASS")
        self.assertEqual(ledger[0]["command_attempt_id"], command_id)
        self.assertEqual(self.manifest_kinds(), [
            "command-record", "fixed-output", "identity", "leak-probe-transcript",
            "passed-preflight-evidence", "passed-preflight-manifest",
            "reservation", "run-record", "shard-claim"])
        # the gate that consumes this manifest (engine/gate.py) still passes
        # it: the kinds it requires kept their names (adversary finding 2)
        from engine import gate
        verdict = gate.check_run_record_manifest(
            canon.load_json(self.path("run-record-manifest.json")), self.a)
        self.assertEqual(verdict["status"], "PASS", verdict)
        # no temporary file is ever a member or a pseudo-shard (finding 12)
        self.assertFalse(any(os.path.basename(m["path"]).startswith(".")
                             for m in canon.load_json(
                                 self.path("run-record-manifest.json"))["members"]))
        self.assertEqual(sorted(os.listdir(self.path(run_reviewer_a.OUTPUTS_DIR))),
                         sorted(f"{s}.json" for s in self.ids))
        self.assertEqual(self.command_record()["reservation_sha256"],
                         canon.file_sha256(self.path(
                             run_reviewer_a.RESERVATIONS_DIR,
                             f"{run_reviewer_a.REVIEW_RESERVATION_PREFIX}{RULING}.json")))
        self.assertIn("REVIEW LEDGER LINE:", self.stdout)
        self.assertIn("| result PASS |", self.stdout)
        self.assertIn("done 2 |", self.stdout)
        states = self.states()
        self.assertEqual({sid: states[sid]["state"] for sid in self.ids},
                         {sid: "DONE" for sid in self.ids})
        self.assertTrue(all(s["problems"] == [] for s in states.values()))
        self.assertEqual(states[self.members[2]["shard_id"]]["state"], "pending")

    def test_order_is_the_rulings_order(self):
        ids = list(reversed(self.ids))
        self.assertEqual(self.review(ids=ids), 0, self.stdout)
        seen = [conformant_output(s.prompts[0])["shard_id"] for s in self.sessions]
        self.assertEqual(seen, ids)
        self.assertEqual([s["shard_id"] for s in self.reservation()["shards"]], ids)

    def test_second_command_needs_a_new_ruling_and_fresh_shards(self):
        self.assertEqual(self.review(), 0, self.stdout)
        self.made.clear()
        # same ruling: refused before anything
        err = str(self.review(ids=[self.members[2]["shard_id"]]))
        self.assertIn("already reserved", err)
        self.assertEqual(self.made, [])
        # new ruling, overlapping shard: refused before reservation
        os.environ[run_reviewer_a.REVIEW_RULING_VAR] = "18376200"
        err = str(self.review(ids=[self.ids[1], self.members[2]["shard_id"]]))
        self.assertIn("already claimed", err)
        self.assertIsNone(self.reservation("18376200"))
        self.assertEqual(self.made, [])
        # new ruling, disjoint shard: runs
        self.assertEqual(self.review(ids=[self.members[2]["shard_id"]]), 0,
                         self.stdout)
        self.assertEqual(len(self.command_records()), 2)
        self.assertEqual(len(self.ledger()), 2)


class StopOnFirstFailure(_ReviewHarness):
    def test_validation_failure_stops_with_no_output(self):
        self.queue.append(GovernedShardSession(response="{}"))
        self.assertEqual(self.review(), 1)
        rec = self.record(self.ids[0])
        self.assertEqual((rec["result"], rec["phase"]), ("FAIL", "validation"))
        self.assertIn("review-execution-failure", rec["error"])
        self.assertIn("completeness", rec["problems"])
        self.assertEqual(rec["cli_invocations"], 1)
        self.assertIsNone(rec["output_sha256"])
        self.assertIsNone(self.output_bytes(self.ids[0]))
        self.assertIsNotNone(self.claim(self.ids[0]))
        self.assert_not_run(self.ids[1])
        self.assertEqual(len(self.made), 1)
        cmd = self.command_record()
        self.assertEqual(cmd["result"], "FAIL")
        self.assertEqual([s["result"] for s in cmd["shards"]], ["FAIL", "NOT_RUN"])
        self.assertIn("not-run 1", self.stdout)
        self.assertEqual(self.states()[self.ids[0]]["state"], "FAIL")
        self.assertEqual(self.states()[self.ids[1]]["state"], "pending")

    def test_non_json_response_is_a_validation_failure_with_the_response_digest(self):
        self.queue.append(GovernedShardSession(response="not json at all"))
        self.assertEqual(self.review(), 1)
        rec = self.record(self.ids[0])
        self.assertEqual((rec["result"], rec["phase"]), ("FAIL", "validation"))
        self.assertIn("output not JSON", rec["error"])
        self.assertEqual(rec["raw_response_sha256"],
                         canon.content_digest("not json at all"))
        self.assertEqual(rec["raw_response"], "not json at all")
        self.assert_not_run(self.ids[1])

    def test_exception_inside_the_call_is_a_spent_invocation(self):
        self.queue.append(RaisingSession(RuntimeError("cli died")))
        self.assertEqual(self.review(), 1)
        rec = self.record(self.ids[0])
        self.assertEqual((rec["result"], rec["phase"]), ("FAIL", "invocation"))
        self.assertIn("harness aborted: RuntimeError: cli died", rec["error"])
        self.assertEqual(rec["cli_invocations"], 1)
        self.assertEqual(rec["live_invocations_started"], 1)
        self.assertEqual(rec["model_calls"], 1)
        self.assertIsNone(rec["session_id"])
        self.assert_not_run(self.ids[1])
        self.assertEqual(self.command_record()["cli_invocations"], 1)

    def test_interrupt_inside_the_call_is_recorded_then_propagated(self):
        self.queue.append(RaisingSession(KeyboardInterrupt()))
        self.review_raises(KeyboardInterrupt)
        rec = self.record(self.ids[0])
        self.assertEqual((rec["result"], rec["phase"]), ("FAIL", "invocation"))
        self.assertIn("KeyboardInterrupt", rec["error"])
        self.assertEqual(rec["cli_invocations"], 1)
        self.assert_not_run(self.ids[1])
        cmd = self.command_record()
        self.assertEqual(cmd["result"], "FAIL")
        self.assertEqual([s["result"] for s in cmd["shards"]], ["FAIL", "NOT_RUN"])
        self.assertEqual(len(self.ledger()), 1)

    def test_session_construction_failure_spends_the_ruling_only(self):
        def factory(system_prompt, cwd, attempts=3):
            self.made.append((cwd, attempts))
            raise RuntimeError("no binary")
        self.assertEqual(self.review(factory=factory), 1)
        self.assertIsNotNone(self.reservation())
        for sid in self.ids:
            self.assert_not_run(sid)
        cmd = self.command_record()
        self.assertEqual([s["result"] for s in cmd["shards"]], ["NOT_RUN", "NOT_RUN"])
        self.assertIn("session construction failed", cmd["shards"][0]["error"])
        self.assertEqual(cmd["model_calls"], 0)
        # the ruling is spent: the same command again is refused
        self.assertIn("already reserved", str(self.review(factory=factory)))

    def test_session_allowing_retries_is_refused_before_the_claim(self):
        def factory(system_prompt, cwd, attempts=3):
            self.made.append((cwd, attempts))
            s = GovernedShardSession(system_prompt)
            s.attempts = 3   # ignores the argument
            self.sessions.append(s)
            return s
        self.assertEqual(self.review(factory=factory), 1)
        self.assertEqual(self.sessions[0].calls, 0)
        for sid in self.ids:
            self.assert_not_run(sid)
        cmd = self.command_record()
        self.assertIn("attempts=3", cmd["shards"][0]["error"])
        self.assertEqual(cmd["shards"][0]["result"], "NOT_RUN")

    def test_session_configuration_drift_is_refused_before_the_claim(self):
        s = GovernedShardSession()
        s.timeout = 5
        self.queue.append(s)
        self.assertEqual(self.review(), 1)
        self.assertEqual(s.calls, 0)
        self.assert_not_run(self.ids[0])
        self.assertIn("configuration differs",
                      self.command_record()["shards"][0]["error"])

    def test_interrupt_before_the_second_shard_leaves_it_not_run(self):
        calls = {"n": 0}

        def factory(system_prompt, cwd, attempts=3):
            calls["n"] += 1
            if calls["n"] == 2:
                raise KeyboardInterrupt()
            s = GovernedShardSession(system_prompt)
            s.attempts = attempts
            self.sessions.append(s)
            return s
        self.review_raises(KeyboardInterrupt, factory=factory)
        self.assertEqual(self.record(self.ids[0])["result"], "DONE")
        self.assertIsNotNone(self.output_bytes(self.ids[0]))
        self.assert_not_run(self.ids[1])
        cmd = self.command_record()
        self.assertEqual([s["result"] for s in cmd["shards"]], ["DONE", "NOT_RUN"])
        self.assertEqual(cmd["result"], "FAIL")


class PolicyPerShard(_ReviewHarness):
    def _fail_in_policy(self, needle):
        self.assertEqual(self.review(), 1)
        rec = self.record(self.ids[0])
        self.assertEqual((rec["result"], rec["phase"]), ("FAIL", "policy"), rec["error"])
        self.assertIn(needle, rec["error"])
        self.assertIsNone(self.output_bytes(self.ids[0]))
        self.assert_not_run(self.ids[1])
        return rec

    def test_two_invocations_for_one_call_fail(self):
        self.queue.append(GovernedShardSession(invocations=2))
        rec = self._fail_in_policy("2 CLI invocation(s) for 1 shard call")
        self.assertEqual(rec["cli_invocations"], 2)

    def test_zero_invocations_fail(self):
        self.queue.append(GovernedShardSession(invocations=0))
        self._fail_in_policy("0 CLI invocation(s)")

    def test_unreported_accounting_fails(self):
        self.queue.append(NoAccountingSession())
        rec = self._fail_in_policy("invocation count unavailable")
        self.assertIsNone(rec["cli_invocations"])

    def test_absent_model_usage_fails(self):
        self.queue.append(GovernedShardSession(usage=ABSENT))
        self._fail_in_policy("no modelUsage reported")

    def test_reviewer_model_absent_fails(self):
        self.queue.append(GovernedShardSession(usage=HAIKU_ONLY))
        self._fail_in_policy("reviewer model fake not reported")

    def test_unaccepted_auxiliary_model_fails_under_reject(self):
        # the fixture identity is bound under policy reject
        self.queue.append(GovernedShardSession(usage=WITH_HAIKU))
        rec = self._fail_in_policy(HAIKU)
        self.assertEqual(rec["auxiliary_model_policy"]["policy"], "reject")
        self.assertEqual(rec["auxiliary_model_violations"],
                         [f"{self.ids[0]}: {HAIKU}"])

    def test_reviewer_model_with_no_tokens_fails(self):
        self.queue.append(GovernedShardSession(usage={
            "fake": {"canonicalModel": "fake", "inputTokens": 0, "outputTokens": 0}}))
        self._fail_in_policy("reported with no tokens")


class OutputInstall(_ReviewHarness):
    def _lying_writer(self, mutate):
        """os.write that, for the shard OUTPUT temporary file only, lands
        `mutate(data)` while reporting the full requested count."""
        real = self.saved_os_write

        def os_write(fd, view):
            data = bytes(view)
            if b'"foundry-pass-2-review-output/' in data[:120]:
                real(fd, mutate(data))
                return len(data)
            return real(fd, view)
        canon.os_write = os_write

    def _fail_in_install(self):
        self.assertEqual(self.review(), 1)
        rec = self.record(self.ids[0])
        self.assertEqual((rec["result"], rec["phase"]), ("FAIL", "install"), rec["error"])
        self.assertIn("output not installed", rec["error"])
        self.assertIsNone(rec["output_sha256"])
        self.assertIsNone(self.output_bytes(self.ids[0]))
        self.assertIsNotNone(self.claim(self.ids[0]))
        self.assertEqual(rec["cli_invocations"], 1)
        self.assert_not_run(self.ids[1])
        outputs = self.path(run_reviewer_a.OUTPUTS_DIR)
        self.assertEqual([n for n in os.listdir(outputs) if not n.startswith(".")], [])
        return rec

    def test_short_landing_with_a_full_count_refuses_at_the_size_check(self):
        self._lying_writer(lambda d: d[:-1])
        rec = self._fail_in_install()
        self.assertIn("byte(s) on disk", rec["error"])

    def test_wrong_bytes_with_the_right_length_refuse_at_the_read_back(self):
        self._lying_writer(lambda d: d[:-2] + b"X\n")
        rec = self._fail_in_install()
        self.assertIn("read back", rec["error"])

    def test_zero_count_refuses(self):
        real = self.saved_os_write

        def os_write(fd, view):
            if b'"foundry-pass-2-review-output/' in bytes(view)[:120]:
                return 0
            return real(fd, view)
        canon.os_write = os_write
        rec = self._fail_in_install()
        self.assertIn("os.write returned 0", rec["error"])

    def test_file_appearing_during_install_is_never_overwritten(self):
        real_link = self.saved["os_link"]
        planted = self.path(run_reviewer_a.OUTPUTS_DIR, f"{self.ids[0]}.json")

        def os_link(src, dst):
            if dst == planted and not os.path.lexists(dst):
                with open(dst, "wb") as f:
                    f.write(b"planted\n")
            return real_link(src, dst)
        run_reviewer_a.os_link = os_link
        self.assertEqual(self.review(), 1)
        rec = self.record(self.ids[0])
        self.assertEqual((rec["result"], rec["phase"]), ("FAIL", "install"))
        self.assertIn("appeared during install", rec["error"])
        with open(planted, "rb") as f:
            self.assertEqual(f.read(), b"planted\n")
        self.assert_not_run(self.ids[1])

    def test_output_is_installed_before_the_record_and_attested_by_it(self):
        # the record names the output's digest and length, so it can only be
        # written after the bytes are on disk; a record with no output is the
        # failure shape, never an output with no record on the success path
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        rec = self.record(self.ids[0])
        out = self.output_bytes(self.ids[0])
        self.assertEqual(rec["output_sha256"], canon.bytes_digest(out))
        self.assertEqual(rec["output_byte_length"], len(out))
        self.assertLessEqual(
            os.lstat(self.path(run_reviewer_a.OUTPUTS_DIR, f"{self.ids[0]}.json")).st_mtime_ns,
            os.lstat(self.path(run_reviewer_a.RUN_RECORDS_DIR,
                               f"{self.ids[0]}.{self.records(self.ids[0])[0][1]}.json")).st_mtime_ns)


class RecordWrittenLast(_ReviewHarness):
    def _patch_record_writer(self, behaviour):
        real = self.saved["write_review_record"]

        def writer(directory, prefix, record):
            return behaviour(real, directory, prefix, record)
        run_reviewer_a.write_review_record = writer

    def test_interrupted_record_write_is_retried_then_the_signal_propagates(self):
        state = {"n": 0}

        def behaviour(real, directory, prefix, record):
            if directory.endswith(run_reviewer_a.RUN_RECORDS_DIR) and state["n"] == 0:
                state["n"] += 1
                raise KeyboardInterrupt()
            return real(directory, prefix, record)
        self._patch_record_writer(behaviour)
        self.review_raises(KeyboardInterrupt)
        rec = self.record(self.ids[0])
        self.assertEqual(rec["result"], "DONE")
        self.assertIn("KeyboardInterrupt", rec["record_write_interrupted"])
        self.assertIsNotNone(self.output_bytes(self.ids[0]))
        self.assert_not_run(self.ids[1])
        cmd = self.command_record()
        self.assertEqual([s["result"] for s in cmd["shards"]], ["DONE", "NOT_RUN"])
        self.assertEqual(cmd["shards"][0]["record_sha256"], self.records(self.ids[0])[0][1])

    def test_record_persisted_then_raising_is_not_written_twice(self):
        def behaviour(real, directory, prefix, record):
            result = real(directory, prefix, record)
            if directory.endswith(run_reviewer_a.RUN_RECORDS_DIR):
                raise OSError("fsync after link")
            return result
        self._patch_record_writer(behaviour)
        self.review_raises(OSError)
        recs = self.records(self.ids[0])
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0][2]["result"], "DONE")
        self.assert_not_run(self.ids[1])
        self.assertEqual(self.command_record()["shards"][0]["record_sha256"], recs[0][1])

    def test_permanently_failing_record_store_leaves_the_shard_unattested(self):
        def behaviour(real, directory, prefix, record):
            if directory.endswith(run_reviewer_a.RUN_RECORDS_DIR):
                raise OSError("record store down")
            return real(directory, prefix, record)
        self._patch_record_writer(behaviour)
        self.review_raises(OSError)
        self.assertEqual(self.records(self.ids[0]), [])
        self.assertIsNotNone(self.claim(self.ids[0]))
        self.assertIsNotNone(self.output_bytes(self.ids[0]))
        cmd = self.command_record()
        self.assertEqual(cmd["shards"][0]["result"], "UNATTESTED")
        self.assertEqual(cmd["shards"][1]["result"], "NOT_RUN")
        self.assertEqual(self.states()[self.ids[0]]["state"], "UNATTESTED")
        # spent: a new ruling naming that shard is refused before reservation
        os.environ[run_reviewer_a.REVIEW_RULING_VAR] = "18376200"
        run_reviewer_a.write_review_record = self.saved["write_review_record"]
        self.made.clear()
        self.assertIn("already claimed", str(self.review(ids=[self.ids[0]])))
        self.assertIsNone(self.reservation("18376200"))

    def test_interrupted_claim_write_spends_the_shard_with_a_record(self):
        real = self.saved_os_write

        def os_write(fd, view):
            if b'"foundry-pass-2-shard-claim/' in bytes(view)[:120]:
                raise KeyboardInterrupt()
            return real(fd, view)
        canon.os_write = os_write
        self.review_raises(KeyboardInterrupt)
        # the claim path exists (possibly empty): spent by existence
        self.assertTrue(os.path.lexists(self.path(run_reviewer_a.CLAIMS_DIR,
                                                  f"{self.ids[0]}.json")))
        rec = self.record(self.ids[0])
        self.assertEqual((rec["result"], rec["phase"]), ("FAIL", "claim"))
        self.assertIn("claim not durably written", rec["error"])
        self.assertEqual(rec["model_calls"], 0)
        self.assertEqual(self.sessions[0].calls, 0)
        self.assert_not_run(self.ids[1])
        self.assertEqual(self.states()[self.ids[0]]["state"], "FAIL")


class TerminalRecordAndIndex(_ReviewHarness):
    def test_manifest_failure_stops_the_command_and_never_masks_the_records(self):
        # the index is refreshed after every terminal shard exit; when that
        # refresh fails the shard's record stays the truth, the command stops,
        # the remainder is NOT_RUN, and the terminal record and ledger are
        # still written (Ari, room 266 gate 5; 18376129: rebuildable index)
        def broken(a_out=None):
            raise OSError("index disk full")
        run_reviewer_a.write_run_record_manifest = broken
        self.assertEqual(self.review(), 1, self.stdout)
        self.assertEqual(self.record(self.ids[0])["result"], "DONE")
        self.assertIsNotNone(self.output_bytes(self.ids[0]))
        self.assert_not_run(self.ids[1])
        cmd = self.command_record()
        self.assertEqual(cmd["result"], "FAIL")
        self.assertEqual([s["result"] for s in cmd["shards"]], ["DONE", "NOT_RUN"])
        self.assertIn("index disk full", cmd["shards"][0]["manifest_error"])
        self.assertIn("manifest not rebuilt after", cmd["error"])
        self.assertEqual(len(self.ledger()), 1)
        self.assertIn("manifest NOT rebuilt", self.stdout)
        self.assertEqual(self.states()[self.ids[0]]["state"], "DONE")

    def test_manifest_is_refreshed_after_every_shard(self):
        seen = []
        real = self.saved["write_run_record_manifest"]

        def counting(a_out=None):
            seen.append(sorted({m["kind"] for m in canon.load_json(
                self.path("run-record-manifest.json"))["members"]})
                        if os.path.lexists(self.path("run-record-manifest.json")) else None)
            return real(a_out)
        run_reviewer_a.write_run_record_manifest = counting
        self.assertEqual(self.review(), 0, self.stdout)
        # after shard 1, after shard 2, and at the terminal exit
        self.assertEqual(len(seen), 3)
        self.assertIn("run-record", self.manifest_kinds())

    def test_inconsistent_evidence_root_refuses_a_new_command(self):
        self.assertEqual(self.review(), 0, self.stdout)
        path = self.path(run_reviewer_a.OUTPUTS_DIR, f"{self.ids[0]}.json")
        with open(path, "ab") as f:
            f.write(b"\n")
        os.environ[run_reviewer_a.REVIEW_RULING_VAR] = "18376200"
        self.made.clear()
        err = str(self.review(ids=[self.members[2]["shard_id"]]))
        self.assertIn("evidence root is inconsistent", err)
        self.assertIn(self.ids[0], err)
        self.assertIsNone(self.reservation("18376200"))
        self.assertEqual(self.made, [])

    def test_status_cross_checks_the_claim_against_the_record(self):
        self.assertEqual(self.review(), 0, self.stdout)
        claim_path = self.path(run_reviewer_a.CLAIMS_DIR, f"{self.ids[1]}.json")
        claim = canon.load_json(claim_path)
        claim["command_attempt_id"] = "forged"
        os.unlink(claim_path)
        canon.write_canonical(claim_path, claim)
        states = self.states()
        self.assertEqual(states[self.ids[1]]["state"], "CORRUPT")
        self.assertIn("claim and record disagree", states[self.ids[1]]["problems"][0])
        # a second record for one shard is a corruption too
        d = self.path(run_reviewer_a.RUN_RECORDS_DIR)
        name = [n for n in os.listdir(d) if n.startswith(self.ids[0] + ".")][0]
        rec = canon.load_json(os.path.join(d, name))
        rec["command_attempt_id"] = "another"
        data = canon.canonical_bytes(rec)
        with open(os.path.join(d, f"{self.ids[0]}.{canon.bytes_digest(data)}.json"), "wb") as f:
            f.write(data)
        states = self.states()
        self.assertEqual(states[self.ids[0]]["state"], "CORRUPT")
        self.assertIn("more than one record", states[self.ids[0]]["problems"][0])


class AdversaryClosures(_ReviewHarness):
    """Each test here reproduces a finding of the isolated adversary on
    this head against the fixed code: the reproduction now fails closed."""

    def test_counts_are_published_on_every_propagating_exit(self):
        # finding 4: the loop's accumulation was skipped when a shard
        # propagated a signal; T and the ledger said calls 0 for a spent call
        self.queue.append(RaisingSession(KeyboardInterrupt()))
        self.review_raises(KeyboardInterrupt)
        rec = self.record(self.ids[0])
        self.assertEqual(rec["cli_invocations"], 1)
        cmd = self.command_record()
        self.assertEqual((cmd["model_calls"], cmd["cli_invocations"]), (1, 1))
        self.assertEqual((self.ledger()[0]["model_calls"],
                          self.ledger()[0]["cli_invocations"]), (1, 1))
        self.assertIn("| calls 1 | invocations 1 ", self.stdout)

    def test_interrupt_inside_the_reservation_write_leaves_a_terminal_record(self):
        # finding 3a: the ruling was spent by existence with nothing on disk
        # saying so
        real = self.saved_os_write

        def os_write(fd, view):
            if b'"foundry-pass-2-review-reservation/' in bytes(view)[:120]:
                raise KeyboardInterrupt()
            return real(fd, view)
        canon.os_write = os_write
        self.review_raises(KeyboardInterrupt)
        self.assertTrue(os.path.lexists(self.path(
            run_reviewer_a.RESERVATIONS_DIR,
            f"{run_reviewer_a.REVIEW_RESERVATION_PREFIX}{RULING}.json")))
        self.assertEqual(self.made, [])
        cmd = self.command_record()
        self.assertEqual(cmd["result"], "FAIL")
        self.assertEqual(cmd["phase"], "reservation")
        self.assertIn("reservation not durably written", cmd["error"])
        self.assertEqual([s["result"] for s in cmd["shards"]], ["NOT_RUN", "NOT_RUN"])
        self.assertEqual(len(self.ledger()), 1)
        canon.os_write = real
        self.assertIn("already reserved", str(self.review()))

    def test_input_edited_after_preverify_is_not_reviewed(self):
        # finding 5: the record attested the manifest's digest while the
        # call re-read the file; now the bytes are re-read, re-hashed, and
        # copied into the private scratch before the claim
        target = os.path.join(self.out, self.members[1]["path"])

        class Rewriting(GovernedShardSession):
            def run(s, prompt):
                shard = canon.load_json(target)
                with open(target, "w", encoding="utf-8") as f:
                    json.dump(shard, f, indent=2)   # same content, other bytes
                return super().run(prompt)
        self.queue.append(Rewriting())
        self.assertEqual(self.review(), 1)
        self.assertEqual(self.record(self.ids[0])["result"], "DONE")
        self.assert_not_run(self.ids[1])
        cmd = self.command_record()
        self.assertEqual(cmd["shards"][1]["result"], "NOT_RUN")
        self.assertIn("input digest drift", cmd["shards"][1]["error"])

    def test_scratch_input_altered_during_the_call_fails_the_shard(self):
        class Tampering(GovernedShardSession):
            def run(s, prompt):
                out = super().run(prompt)
                scratch = os.path.join(s.cwd, "shard.json")
                with open(scratch, "ab") as f:
                    f.write(b"\n")
                return out
        t = Tampering()
        self.queue.append(t)

        def factory(system_prompt, cwd, attempts=3):
            self.made.append((cwd, attempts))
            s = self.queue.pop(0) if self.queue else GovernedShardSession(system_prompt)
            s.attempts = attempts
            s.cwd = cwd
            self.sessions.append(s)
            return s
        self.assertEqual(self.review(factory=factory), 1)
        rec = self.record(self.ids[0])
        self.assertEqual((rec["result"], rec["phase"]), ("FAIL", "policy"))
        self.assertIn("altered during the call", rec["error"])
        self.assertIsNone(self.output_bytes(self.ids[0]))

    def test_session_model_and_late_configuration_change_are_refused(self):
        # finding 8: command() was read once and model never
        s = GovernedShardSession()
        s.model = "claude-haiku-4-5"
        self.queue.append(s)
        self.assertEqual(self.review(), 1)
        self.assertEqual(s.calls, 0)
        self.assert_not_run(self.ids[0])
        self.assertIn("session model", self.command_record()["shards"][0]["error"])

        class Switching(GovernedShardSession):
            def run(s2, prompt):
                out = super().run(prompt)
                s2.command = lambda: ["/somewhere/else/claude", "--model", "evil", "-p", "x"]
                return out
        os.environ[run_reviewer_a.REVIEW_RULING_VAR] = "18376200"
        self.made.clear()
        self.queue.append(Switching())
        self.assertEqual(self.review(), 1)
        rec = self.record(self.ids[0])
        self.assertEqual((rec["result"], rec["phase"]), ("FAIL", "policy"))
        self.assertIn("after the call, session configuration differs", rec["error"])
        self.assertIsNone(self.output_bytes(self.ids[0]))

    def test_system_exit_from_a_session_never_becomes_the_exit_status(self):
        # finding 9: a session raising SystemExit(0) made a failed command
        # exit 0
        self.queue.append(RaisingSession(SystemExit(0)))
        code = self.review()
        self.assertNotEqual(code, 0)
        self.assertIn("review failed", str(code))
        self.assertEqual(self.record(self.ids[0])["result"], "FAIL")
        self.assertEqual(self.command_record()["result"], "FAIL")

    def test_ledger_failure_is_on_the_line_and_in_the_exit_status(self):
        # finding 10: a ledger failure lost the line, the manifest, and the exit
        ledger = self.path(run_reviewer_a.REVIEW_LEDGER)

        class Planting(GovernedShardSession):
            def run(s, prompt):
                os.symlink(os.path.join(os.path.dirname(ledger), "elsewhere.json"), ledger)
                return super().run(prompt)
        self.queue.append(Planting())
        self.assertEqual(self.review(ids=[self.ids[0]]), 1)
        self.assertEqual(self.command_record()["result"], "PASS")
        self.assertIn("ledger NOT appended (PathBoundaryError)", self.stdout)
        self.assertIn("| result PASS |", self.stdout)
        self.assertFalse(os.path.lexists(self.path("elsewhere.json")))
        self.assertIn("run-record", self.manifest_kinds())

    def test_a_planted_file_at_a_record_directory_name_cannot_land_mid_command(self):
        # finding 3b: the directories exist as real directories before the
        # reservation, so a session cannot put a file where T must go
        target = self.path(run_reviewer_a.COMMAND_RECORDS_DIR)

        class Planting(GovernedShardSession):
            def run(s, prompt):
                with open(target, "w") as f:   # a directory: this raises
                    f.write("x")
                return super().run(prompt)
        self.queue.append(Planting())
        self.assertEqual(self.review(), 1)
        self.assertTrue(canon.is_real_dir(target))
        cmd = self.command_record()
        self.assertEqual([s["result"] for s in cmd["shards"]], ["FAIL", "NOT_RUN"])
        self.assertIn("IsADirectoryError", cmd["shards"][0]["error"])

    def test_status_recomputes_every_relationship_the_record_asserts(self):
        # finding 6: a record rewritten with a fabricated ruling, command,
        # identity, response, and count, renamed to its new digest, passed
        # as DONE with no problems
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        d = self.path(run_reviewer_a.RUN_RECORDS_DIR)
        name = [n for n in os.listdir(d) if n.startswith(self.ids[0] + ".")][0]
        original = canon.load_json(os.path.join(d, name))

        def rewritten(**changes):
            for n in os.listdir(d):
                os.unlink(os.path.join(d, n))
            rec = dict(original, **changes)
            data = canon.canonical_bytes(rec)
            with open(os.path.join(d, f"{self.ids[0]}.{canon.bytes_digest(data)}.json"), "wb") as f:
                f.write(data)
            return self.states()[self.ids[0]]
        for changes, needle in (
                ({"raw_response": "I never said this"}, "raw response does not hash"),
                ({"ruling_id": "999999", "reservation_path":
                  "reservations/review-ruling-999999.json"}, "reservation the record names is absent"),
                ({"command_attempt_id": "00000000-0000-0000-0000-000000000000"},
                 "reservation and record disagree on command_attempt_id"),
                ({"model_id": "claude-opus-9-jailbroken", "ruled_model_id":
                  "claude-opus-9-jailbroken"}, "disagree on model_id"),
                ({"head": "c" * 40}, "disagree on head"),
                ({"configuration_sha256": "0" * 64}, "disagree on configuration_sha256"),
                ({"auxiliary_model_policy": dict(original["auxiliary_model_policy"],
                                                 policy="accept", auxiliary_model="x")},
                 "disagree on auxiliary_model_policy"),
                ({"cli_invocations": 99}, "does not satisfy the ruling's sentence"),
                ({"claim_sha256": "0" * 64}, "claim bytes do not hash")):
            st = rewritten(**changes)
            self.assertEqual(st["state"], "CORRUPT", (changes, st))
            self.assertTrue(any(needle in p for p in st["problems"]), (needle, st["problems"]))
        # the terminal record's listing is recomputed too
        rewritten()
        self.assertEqual(self.states()[self.ids[0]]["state"], "DONE")
        cdir = self.path(run_reviewer_a.COMMAND_RECORDS_DIR)
        for n in os.listdir(cdir):
            os.unlink(os.path.join(cdir, n))
        st = self.states()[self.ids[0]]
        self.assertEqual(st["state"], "CORRUPT")
        self.assertIn("no terminal command record", st["problems"][0])
        cmds = run_reviewer_a.command_states(self.a)
        self.assertEqual(cmds[0]["problems"], ["no terminal command record (unfinalized)"])
        os.environ[run_reviewer_a.REVIEW_RULING_VAR] = "18376200"
        self.made.clear()
        self.assertIn("no terminal command record", str(self.review(ids=[self.ids[1]])))
        self.assertEqual(self.made, [])


class SecondPassClosures(_ReviewHarness):
    """Each test reproduces a finding of the second isolated pass against
    the fixed code."""

    def test_refused_output_bytes_never_reach_the_outputs_directory(self):
        # finding 1: a refused install quarantined its bytes inside outputs/
        # under <sid>-REFUSED-*.json, which the gate read as a fixed output
        # the bytes land correctly and are linked into place, then differ at
        # the final no-follow read (something rewrote them through the
        # installed name): the install is refused and the bytes quarantined
        real_link = self.saved["os_link"]
        target = self.path(run_reviewer_a.OUTPUTS_DIR, f"{self.ids[0]}.json")

        def os_link(src, dst):
            real_link(src, dst)
            if dst == target:
                with open(dst, "r+b") as f:
                    f.seek(-2, os.SEEK_END)
                    f.write(b"X\n")
        run_reviewer_a.os_link = os_link
        self.assertEqual(self.review(ids=[self.ids[0]]), 1)
        run_reviewer_a.os_link = real_link
        rec = self.record(self.ids[0])
        self.assertEqual((rec["result"], rec["phase"]), ("FAIL", "install"))
        self.assertIn("moved to REFUSED-output-", rec["error"])
        self.assertEqual([n for n in os.listdir(self.path(run_reviewer_a.OUTPUTS_DIR))
                          if not n.startswith(".")], [])
        quarantined = [n for n in os.listdir(self.a) if n.startswith("REFUSED-output-")]
        self.assertEqual(len(quarantined), 1, quarantined)
        from engine import gate
        self.assertEqual(gate.load_outputs(
            self.path(run_reviewer_a.OUTPUTS_DIR), {}, {"shards": []}, {},
            lambda o: (True, {}))[1], [])
        self.assertNotIn(self.ids[0][:-1], run_reviewer_a.claimed_shard_ids(self.a) - {self.ids[0]})
        # the quarantine blocks the next command until a maintainer looks
        os.environ[run_reviewer_a.REVIEW_RULING_VAR] = "18376200"
        self.made.clear()
        err = str(self.review(ids=[self.ids[1]]))
        self.assertIn("quarantined bytes from a refused install", err)
        self.assertEqual(self.made, [])

    def test_a_refused_named_file_planted_in_outputs_is_refused(self):
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        planted = self.path(run_reviewer_a.OUTPUTS_DIR,
                            f"{self.ids[1]}-REFUSED-20260101T000000Z-0.json")
        shutil.copy(self.path(run_reviewer_a.OUTPUTS_DIR, f"{self.ids[0]}.json"), planted)
        # not a member, not a spent id, and the root refuses a new command
        run_reviewer_a.write_run_record_manifest(self.a)
        self.assertNotIn(os.path.basename(planted),
                         [os.path.basename(m["path"]) for m in canon.load_json(
                             self.path("run-record-manifest.json"))["members"]])
        os.environ[run_reviewer_a.REVIEW_RULING_VAR] = "18376200"
        self.made.clear()
        err = str(self.review(ids=[self.ids[1]]))
        self.assertIn("not a shard output the harness wrote", err)
        self.assertEqual(self.made, [])

    def test_reservation_rewritten_after_the_fact_is_corrupt(self):
        # finding 2: the reservation was never recomputed
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        path = self.path(run_reviewer_a.RESERVATIONS_DIR,
                         f"{run_reviewer_a.REVIEW_RESERVATION_PREFIX}{RULING}.json")
        original = canon.load_json(path)
        for changes, needle in (
                ({"model_id": "claude-opus-9-jailbroken",
                  "ruled_model_id": "claude-opus-9-jailbroken"}, "model_id"),
                ({"head": "c" * 40}, "head"),
                ({"configuration_sha256": "0" * 64}, "configuration_sha256"),
                ({"call_ceiling": 99}, "ceiling"),
                ({"auxiliary_model_policy": dict(original["auxiliary_model_policy"],
                                                 policy="accept", auxiliary_model="x")},
                 "auxiliary_model_policy"),
                ({"bindings": {}}, "bindings")):
            os.unlink(path)
            canon.write_canonical(path, dict(original, **changes))
            st = self.states()[self.ids[0]]
            self.assertEqual(st["state"], "CORRUPT", (changes, st))
            self.assertTrue(any(needle in p for p in st["problems"]), (needle, st["problems"]))
            cmd = run_reviewer_a.command_states(self.a)[0]
            self.assertTrue(cmd["problems"], (changes, cmd))
        # the same content in other bytes: the claim and T pin the digest
        os.unlink(path)
        with open(path, "wb") as f:
            f.write(canon.canonical_bytes(original) + b"\n")
        st = self.states()[self.ids[0]]
        self.assertEqual(st["state"], "CORRUPT", st)
        # each pin on its own: the claim's, the shard record's terminal
        # record's, and the command record's
        self.assertIn("the claim's reservation digest is not the reservation on disk",
                      st["problems"])
        self.assertIn("the terminal command record's reservation digest is not the "
                      "reservation on disk", st["problems"])
        self.assertIn("command record's reservation digest is not the reservation on disk",
                      run_reviewer_a.command_states(self.a)[0]["problems"])

    def test_record_plus_terminal_record_edit_is_held_against_the_reservation(self):
        # finding 3: a two-file rewrite made a DONE record attest another model
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        d = self.path(run_reviewer_a.RUN_RECORDS_DIR)
        cdir = self.path(run_reviewer_a.COMMAND_RECORDS_DIR)
        name = [n for n in os.listdir(d) if n.startswith(self.ids[0] + ".")][0]
        rec = canon.load_json(os.path.join(d, name))
        rec.update(model_id="claude-opus-9-jailbroken", ruled_model_id="claude-opus-9-jailbroken",
                   head="c" * 40, configuration_sha256="0" * 64)
        data = canon.canonical_bytes(rec)
        os.unlink(os.path.join(d, name))
        new_sha = canon.bytes_digest(data)
        with open(os.path.join(d, f"{self.ids[0]}.{new_sha}.json"), "wb") as f:
            f.write(data)
        cname = os.listdir(cdir)[0]
        cmd = canon.load_json(os.path.join(cdir, cname))
        cmd["shards"][0]["record_sha256"] = new_sha
        cmd.update(model_id="claude-opus-9-jailbroken", ruled_model_id="claude-opus-9-jailbroken",
                   head="c" * 40, configuration_sha256="0" * 64)
        cdata = canon.canonical_bytes(cmd)
        os.unlink(os.path.join(cdir, cname))
        with open(os.path.join(cdir, f"{cmd['command_attempt_id']}.{canon.bytes_digest(cdata)}.json"), "wb") as f:
            f.write(cdata)
        st = self.states()[self.ids[0]]
        self.assertEqual(st["state"], "CORRUPT", st)
        self.assertTrue(any("reservation and record disagree on model_id" in p
                            for p in st["problems"]), st["problems"])
        self.assertTrue(any("differs from the identity on disk" in p
                            for p in st["problems"]), st["problems"])
        self.assertTrue(run_reviewer_a.command_states(self.a)[0]["problems"])

    def test_signal_after_the_reservation_before_the_loop_leaves_T(self):
        # finding 4: the two statements between the reservation and the
        # loop were outside every handler
        real_sha = run_reviewer_a._sha

        def sha(path):
            if os.path.basename(path).startswith(run_reviewer_a.REVIEW_RESERVATION_PREFIX):
                raise KeyboardInterrupt()
            return real_sha(path)
        run_reviewer_a._sha = sha
        try:
            self.review_raises(KeyboardInterrupt)
        finally:
            run_reviewer_a._sha = real_sha
        cmd = self.command_record()
        self.assertEqual(cmd["result"], "FAIL")
        self.assertEqual([s["result"] for s in cmd["shards"]], ["NOT_RUN", "NOT_RUN"])
        self.assertEqual(self.made, [])
        self.assertIn("REVIEW LEDGER LINE", self.stdout)

    def test_malformed_record_is_corrupt_not_a_crash(self):
        # finding 5
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        d = self.path(run_reviewer_a.RUN_RECORDS_DIR)
        name = [n for n in os.listdir(d) if n.startswith(self.ids[0] + ".")][0]
        rec = canon.load_json(os.path.join(d, name))
        rec["observed_model_usage"] = [{"models": {"not": "a list"}, "model_usage_reported": True}]
        data = canon.canonical_bytes(rec)
        os.unlink(os.path.join(d, name))
        with open(os.path.join(d, f"{self.ids[0]}.{canon.bytes_digest(data)}.json"), "wb") as f:
            f.write(data)
        st = self.states()[self.ids[0]]
        self.assertEqual(st["state"], "CORRUPT")
        self.assertTrue(any("malformed" in p for p in st["problems"]), st["problems"])
        os.environ[run_reviewer_a.REVIEW_RULING_VAR] = "18376200"
        self.made.clear()
        self.assertIn("inconsistent", str(self.review(ids=[self.ids[1]])))

    def test_symlinked_directory_component_is_refused(self):
        # finding 6
        outside = os.path.join(self.root, "outside")
        os.makedirs(outside)
        shutil.copy(os.path.join(self.out, self.members[1]["path"]),
                    os.path.join(outside, "x.json"))
        os.symlink(outside, os.path.join(self.out, "elsewhere"))
        shards = [dict(m) for m in self.members]
        shards[1] = dict(shards[1], path="elsewhere/x.json")
        self._rewrite_manifest(shards)
        err = str(self.review())
        self.assertIn("through a non-directory or a link", err)
        self.assert_nothing_reserved()

    def test_leftover_temporary_in_the_root_refuses_the_next_command(self):
        # finding 7
        with open(self.path(".tmp-record-leftover.json"), "w") as f:
            f.write("{}")
        err = str(self.review())
        self.assertIn(".tmp-record-leftover.json: leftover temporary file", err)
        self.assert_nothing_reserved()

    def test_interrupt_in_the_ledger_prints_the_whole_line(self):
        # note 12
        real = run_reviewer_a.append_ledger

        def interrupted(*args, **kwargs):
            raise KeyboardInterrupt()
        run_reviewer_a.append_ledger = interrupted
        try:
            self.review_raises(KeyboardInterrupt, ids=[self.ids[0]])
        finally:
            run_reviewer_a.append_ledger = real
        self.assertIn("REVIEW LEDGER LINE:", self.stdout)
        self.assertIn(f"head {HEAD} | ruling {RULING}", self.stdout)
        self.assertIn("ledger NOT appended (KeyboardInterrupt) (interrupted", self.stdout)
        self.assertEqual(self.command_record()["result"], "PASS")


class OverlappingCommands(_ReviewHarness):
    def test_a_shard_claimed_by_another_command_after_precheck_is_not_run(self):
        # Ari, room 266: two overlapping commands past precheck; exactly one
        # claim can win. The loser constructs its session, finds the claim
        # taken at claim time, makes no call, writes no record under the
        # winner's shard, and stops with the shard NOT_RUN
        winner = self.path(run_reviewer_a.CLAIMS_DIR, f"{self.ids[1]}.json")

        def factory(system_prompt, cwd, attempts=3):
            self.made.append((cwd, attempts))
            if len(self.made) == 2:
                os.makedirs(os.path.dirname(winner), exist_ok=True)
                canon.write_canonical(winner, {"shard_id": self.ids[1],
                                               "command_attempt_id": "other-command"})
            s = GovernedShardSession(system_prompt)
            s.attempts = attempts
            self.sessions.append(s)
            return s
        self.assertEqual(self.review(factory=factory), 1)
        self.assertEqual(self.record(self.ids[0])["result"], "DONE")
        self.assertEqual(self.sessions[1].calls, 0)
        self.assertEqual(self.records(self.ids[1]), [])
        self.assertIsNone(self.output_bytes(self.ids[1]))
        self.assertEqual(canon.load_json(winner)["command_attempt_id"], "other-command")
        cmd = self.command_record()
        self.assertEqual([s["result"] for s in cmd["shards"]], ["DONE", "NOT_RUN"])
        self.assertIn("claimed by another command", cmd["shards"][1]["error"])
        self.assertEqual(cmd["model_calls"], 1)

    def test_status_rebuilds_from_artifacts_and_detects_drift(self):
        self.assertEqual(self.review(), 0, self.stdout)
        os.unlink(self.path("run-record-manifest.json"))
        os.unlink(self.path(run_reviewer_a.REVIEW_LEDGER))
        states = self.states()
        self.assertEqual([states[s]["state"] for s in self.ids], ["DONE", "DONE"])
        # an edited output no longer matches the record's attestation
        path = self.path(run_reviewer_a.OUTPUTS_DIR, f"{self.ids[0]}.json")
        with open(path, "ab") as f:
            f.write(b"\n")
        states = self.states()
        self.assertEqual(states[self.ids[0]]["state"], "CORRUPT")
        self.assertIn("does not match the record's attestation",
                      states[self.ids[0]]["problems"][0])
        # a record whose bytes no longer hash to its name
        d = self.path(run_reviewer_a.RUN_RECORDS_DIR)
        name = [n for n in os.listdir(d) if n.startswith(self.ids[1] + ".")][0]
        rec = canon.load_json(os.path.join(d, name))
        rec["result"] = "DONE"
        rec["error"] = "edited"
        with open(os.path.join(d, name), "wb") as f:
            f.write(canon.canonical_bytes(rec))
        states = self.states()
        self.assertEqual(states[self.ids[1]]["state"], "CORRUPT")
        self.assertIn("does not hash to its name", states[self.ids[1]]["problems"][0])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            run_reviewer_a.status(self.out, self.a)
        self.assertIn("CORRUPT", buf.getvalue())
        self.assertIn("PROBLEMS", buf.getvalue())

    def test_command_record_lists_every_named_shard_with_its_record(self):
        ids = [m["shard_id"] for m in self.members[:3]]
        self.queue.extend([GovernedShardSession(), GovernedShardSession(response="{}")])
        self.assertEqual(self.review(ids=ids), 1)
        cmd = self.command_record()
        self.assertEqual([s["shard_id"] for s in cmd["shards"]], ids)
        self.assertEqual([s["result"] for s in cmd["shards"]],
                         ["DONE", "FAIL", "NOT_RUN"])
        self.assertEqual(cmd["shards"][0]["record_sha256"], self.records(ids[0])[0][1])
        self.assertEqual(cmd["shards"][1]["record_sha256"], self.records(ids[1])[0][1])
        self.assertIsNone(cmd["shards"][2]["record_sha256"])
        self.assertEqual(cmd["call_ceiling"], 3)
        self.assertEqual(cmd["model_calls"], 2)
        self.assertEqual(cmd["reservation_sha256"], canon.file_sha256(self.path(
            run_reviewer_a.RESERVATIONS_DIR,
            f"{run_reviewer_a.REVIEW_RESERVATION_PREFIX}{RULING}.json")))
        self.assertEqual(self.ledger()[0]["shards"][2]["result"], "NOT_RUN")
        self.assertEqual(len(self.made), 2)


class ExistingCallersUnchanged(unittest.TestCase):
    def test_default_evidence_gate_still_refuses_review_directories(self):
        root = tempfile.mkdtemp(prefix="gate-")
        try:
            q = os.path.join(root, "q")
            os.makedirs(os.path.join(q, "run-records"))
            problems = run_reviewer_a.check_evidence_paths(q, root=root)
            self.assertEqual(problems, ["run-records is a directory, not a regular file"])
            self.assertEqual(run_reviewer_a.check_evidence_paths(
                q, root=root, allowed_dirs=run_reviewer_a.REVIEW_EVIDENCE_DIRS), [])
            os.symlink(root, os.path.join(q, "run-records", "link.json"))
            self.assertEqual(run_reviewer_a.check_evidence_paths(
                q, root=root, allowed_dirs=run_reviewer_a.REVIEW_EVIDENCE_DIRS),
                ["run-records/link.json is a symlink, not a regular file"])
        finally:
            shutil.rmtree(root)

    def test_reserve_head_keeps_its_words(self):
        root = tempfile.mkdtemp(prefix="reserve-")
        try:
            head = "a" * 40
            run_reviewer_a.reserve_head(root, head, {"reserved_utc": "now"})
            with self.assertRaises(SystemExit) as ctx:
                run_reviewer_a.reserve_head(root, head, {"reserved_utc": "now"})
            self.assertIn(f"head {head} is already reserved", str(ctx.exception))
            self.assertIn("a new attempt needs a new exact commit", str(ctx.exception))
            meta = canon.load_json(os.path.join(root, "reservations", f"{head}.json"))
            self.assertEqual(meta["head"], head)
            self.assertEqual(meta["artifact_version"],
                             "foundry-pass-2-qualification-reservation/experimental-v0.1")
        finally:
            shutil.rmtree(root)


if __name__ == "__main__":
    unittest.main()
