"""Offline checks of the reviewer harness using a fake session: the output
checks (completeness, digest preservation, schema via Ari's validator,
fence stripping) without any model call."""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PASS2 = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PASS2, "tools"))

from engine import canon, reviewer  # noqa: E402
import run_reviewer_a  # noqa: E402
try:  # `discover -s tests -t .` imports as a package; direct runs do not
    from tests.test_identity_binding import bind_fixture_identity, HEAD as BOUND_HEAD  # noqa: E402
except ImportError:
    sys.path.insert(0, HERE)
    from test_identity_binding import bind_fixture_identity, HEAD as BOUND_HEAD  # noqa: E402

OUT = os.path.join(PASS2, os.environ.get("FOUNDRY_PASS2_OUT", "out"))  # CI: out-fixture


class FakeSession:
    model = "fake"

    def __init__(self, response):
        self.response = response

    calls = 0

    def run(self, prompt):
        self.calls += 1
        self.prompt = prompt
        return {"result": self.response, "session_id": "fake-1",
                "num_turns": 1}


def synthetic_output(shard, digests, verdict="accept"):
    dispositions = []
    for r in shard["records"]:
        d = {"artifact_id": r["artifact_id"],
             "record_sha256": r["record_sha256"],
             "claim_payload_sha256": r["claim_payload_sha256"],
             "normalized_support_anchor_set_sha256":
                 r["normalized_support_anchor_set_sha256"],
             "verdict": verdict, "rationale": "synthetic",
             "reason_codes": [] if verdict == "accept" else ["other-material-error"],
             "proposed_correction": None}
        dispositions.append(d)
    return {
        "artifact_version": "foundry-pass-2-review-output/experimental-v0.1",
        "contract_sha256": digests["CONTRACT_SHA256"],
        "review_input_bundle_sha256": digests["REVIEW_INPUT_BUNDLE_SHA256"],
        "shard_manifest_sha256": digests["SHARD_MANIFEST_SHA256"],
        "reviewer_identity_sha256": digests["REVIEWER_IDENTITY_SHA256"],
        "shard_id": shard["shard_id"],
        "dispositions": dispositions,
        "completeness": {"input_artifact_count": len(dispositions),
                         "output_disposition_count": len(dispositions),
                         "duplicate_artifact_ids": [], "missing_artifact_ids": [],
                         "unexpected_artifact_ids": []},
    }


class ReviewShardChecks(unittest.TestCase):
    def setUp(self):
        self.digests = dict(run_reviewer_a.bundle_digests(),
                            REVIEWER_IDENTITY_SHA256="f" * 64)
        manifest = canon.load_json(os.path.join(OUT, "shard-manifest.json"))
        self.member = next(m for m in manifest["shards"]
                           if m["shard_id"] == "shard-141.202")
        self.shard_path = os.path.join(OUT, self.member["path"])
        self.shard = canon.load_json(self.shard_path)
        with open(os.path.join(PASS2, "evaluator", "ari",
                               "reviewer-task-template-v0.1.md")) as f:
            self.template = f.read()
        self.schema = run_reviewer_a.load_schema(OUT)

    def run_with(self, response):
        session = FakeSession(response)
        return reviewer.review_shard(
            session, self.template, self.digests, self.shard_path,
            self.member["artifact_ids"], run_reviewer_a.schema_validator,
            self.schema)

    # 18206224 item 1 / ruling 18206234: deterministic identity gate before
    # any model call, real-review path.
    def _corrupt_shard(self, mutate):
        import copy, tempfile
        shard = copy.deepcopy(self.shard)
        mutate(shard["records"][0])
        d = tempfile.mkdtemp(prefix="foundry-corrupt-shard-")
        path = os.path.join(d, "shard.json")
        canon.write_canonical(path, shard)
        return path

    def _assert_stops_before_call(self, mutate, problem):
        path = self._corrupt_shard(mutate)
        session = FakeSession("{}")
        with self.assertRaisesRegex(reviewer.ReviewerError,
                                    "record-identity-failed.*" + problem):
            reviewer.review_shard(session, self.template, self.digests, path,
                                  self.member["artifact_ids"],
                                  run_reviewer_a.schema_validator, self.schema)
        self.assertEqual(session.calls, 0)

    def test_corrupt_record_digest_stops_before_model_call(self):
        self._assert_stops_before_call(
            lambda r: r.__setitem__("record_sha256", "0" * 64),
            "record-digest-mismatch")

    def test_corrupt_artifact_id_stops_before_model_call(self):
        self._assert_stops_before_call(
            lambda r: r.__setitem__("artifact_id", "f2r-" + "0" * 24),
            "artifact-id-derivation-mismatch")

    def test_corrupt_payload_digest_stops_before_model_call(self):
        self._assert_stops_before_call(
            lambda r: r.__setitem__("claim_payload_sha256", "1" * 64),
            "payload-digest-mismatch")

    def test_corrupt_anchor_set_digest_stops_before_model_call(self):
        self._assert_stops_before_call(
            lambda r: r.__setitem__("normalized_support_anchor_set_sha256",
                                    "2" * 64),
            "anchor-set-digest-mismatch")

    def test_corrupt_quote_span_stops_before_model_call(self):
        def mutate(r):
            r["evidence"][0]["exact_text"] = r["evidence"][0]["exact_text"] + "x"
        self._assert_stops_before_call(mutate, "quote")

    def test_record_missing_field_is_typed_hard_stop(self):
        self._assert_stops_before_call(
            lambda r: r.__delitem__("claim_payload"), "malformed")

    def test_empty_shard_is_typed_hard_stop(self):
        import copy, tempfile
        shard = copy.deepcopy(self.shard)
        shard["records"] = []
        d = tempfile.mkdtemp(prefix="foundry-empty-shard-")
        path = os.path.join(d, "shard.json")
        canon.write_canonical(path, shard)
        session = FakeSession("{}")
        with self.assertRaisesRegex(reviewer.ReviewerError, "no records"):
            reviewer.review_shard(session, self.template, self.digests, path,
                                  [], run_reviewer_a.schema_validator,
                                  self.schema)
        self.assertEqual(session.calls, 0)

    def test_clean_shard_records_verification_in_run_record(self):
        out = synthetic_output(self.shard, self.digests)
        rec = self.run_with(json.dumps(out))
        ver = rec["pre_call_record_verification"]
        self.assertEqual(len(ver), len(self.shard["records"]))
        self.assertTrue(all(v["verdict"] == "verified" for v in ver))

    # discussioncomment-18206472: orchestration-level hard stop. Two selected
    # shards; corrupt the first, then the second; the review command must
    # exit on the identity failure with ZERO sessions across the selection.
    def _review_fixture(self, corrupt_index):
        import copy, shutil, tempfile
        root = tempfile.mkdtemp(prefix="foundry-orch-")
        out_root = os.path.join(root, "out")
        shutil.copytree(OUT, out_root)
        manifest_path = os.path.join(out_root, "shard-manifest.json")
        manifest = canon.load_json(manifest_path)
        selected = manifest["shards"][:2]
        if corrupt_index is not None:
            member = selected[corrupt_index]
            shard_path = os.path.join(out_root, member["path"])
            shard = canon.load_json(shard_path)
            shard["records"][0]["record_sha256"] = "0" * 64
            canon.write_canonical(shard_path, shard)
            # manifest kept consistent with the corrupt bytes so the failure
            # is the record-identity gate, not the shard-digest check; and
            # the bundle's declaration kept consistent with the manifest, so
            # the failure is not the bound-manifest digest check either
            member["sha256"] = canon.file_sha256(shard_path)
            canon.write_canonical(manifest_path, manifest)
            bundle_path = os.path.join(out_root, "review-input-bundle.json")
            bundle = canon.load_json(bundle_path)
            bundle["shard_manifest"]["sha256"] = canon.file_sha256(manifest_path)
            canon.write_canonical(bundle_path, bundle)
        a_out = os.path.join(root, "reviewer-a")
        os.makedirs(a_out)
        # review() now enforces the bound head, harness, model, CLI build,
        # configuration, and evidence (18371886): the fixture identity is
        # bound for real, with a fake session and the stubs the binding
        # tests use, so it carries every bound field
        bind_fixture_identity(out_root, a_out)
        return out_root, a_out

    def _run_review_counting_sessions(self, out_root, a_out):
        """One governed command over the first two shard IDs (18376129:
        selection by explicit IDs under a ruling reference), with a
        conformant one-attempt session per shard. Returns the scratch
        directories handed to sessions and the exit: None on a PASS (exit
        0), the refusal text otherwise."""
        import contextlib, io
        try:
            from tests.test_review_governance import GovernedShardSession
        except ImportError:
            from test_review_governance import GovernedShardSession
        made = []

        def factory(system_prompt, cwd, attempts=run_reviewer_a.REVIEW_ATTEMPTS):
            made.append(cwd)
            s = GovernedShardSession(system_prompt)
            s.attempts = attempts
            return s
        saved = {k: getattr(run_reviewer_a, k)
                 for k in ("git_head", "cli_version", "MODEL")}
        run_reviewer_a.git_head = lambda what="qualification": (BOUND_HEAD, True)
        run_reviewer_a.cli_version = lambda: "fake-cli"
        run_reviewer_a.MODEL = "fake"
        os.environ[run_reviewer_a.REVIEW_RULED_MODEL_VAR] = "fake"
        os.environ[run_reviewer_a.REVIEW_RULING_VAR] = "18376129"
        manifest = canon.load_json(os.path.join(out_root, "shard-manifest.json"))
        ids = [m["shard_id"] for m in manifest["shards"][:2]]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                run_reviewer_a.review(ids, session_factory=factory,
                                      out_root=out_root, a_out=a_out)
        except SystemExit as err:
            return made, (None if err.code == 0 else str(err))
        finally:
            for k, v in saved.items():
                setattr(run_reviewer_a, k, v)
            os.environ.pop(run_reviewer_a.REVIEW_RULED_MODEL_VAR, None)
            os.environ.pop(run_reviewer_a.REVIEW_RULING_VAR, None)
        return made, None

    def test_review_aborts_before_any_session_when_first_shard_corrupt(self):
        out_root, a_out = self._review_fixture(0)
        made, err = self._run_review_counting_sessions(out_root, a_out)
        self.assertEqual(made, [])
        self.assertIn("aborted before any session", err)
        self.assertIn("record-identity-failed", err)
        # nothing reserved, claimed, or recorded: the abort precedes the
        # command reservation
        for sub in ("run-records", "claims", "outputs", "command-records"):
            self.assertFalse(os.path.lexists(os.path.join(a_out, sub)))
        self.assertEqual([n for n in os.listdir(os.path.join(a_out, "reservations"))
                          if n.startswith("review-")], [])

    def test_review_aborts_before_any_session_when_second_shard_corrupt(self):
        out_root, a_out = self._review_fixture(1)
        made, err = self._run_review_counting_sessions(out_root, a_out)
        self.assertEqual(made, [])
        self.assertIn("aborted before any session", err)
        self.assertIn("record-identity-failed", err)
        for sub in ("run-records", "claims", "outputs", "command-records"):
            self.assertFalse(os.path.lexists(os.path.join(a_out, sub)))

    def test_review_preverifies_then_creates_one_session_per_shard(self):
        out_root, a_out = self._review_fixture(None)
        made, err = self._run_review_counting_sessions(out_root, a_out)
        self.assertIsNone(err, err)
        self.assertEqual(len(made), 2)
        self.assertEqual(len(set(made)), 2)   # a fresh scratch dir per shard
        self.assertEqual(len(os.listdir(os.path.join(a_out, "outputs"))), 2)
        self.assertEqual(len(os.listdir(os.path.join(a_out, "run-records"))), 2)

    def test_second_qualification_on_ledgered_head_is_refused(self):
        import tempfile
        d = tempfile.mkdtemp(prefix="foundry-ledger-")
        ledger = os.path.join(d, "qualification-ledger.json")
        canon.write_canonical(ledger, {
            "artifact_version": "foundry-pass-2-qualification-ledger/experimental-v0.1",
            "attempts": [{"attempt_id": "a-1", "head": "c" * 40,
                          "result": "FAIL"}]})
        with self.assertRaisesRegex(SystemExit, "already has 1 ledgered"):
            run_reviewer_a.refuse_if_ledgered(ledger, "c" * 40)
        run_reviewer_a.refuse_if_ledgered(ledger, "d" * 40)  # new head: ok
        run_reviewer_a.refuse_if_ledgered(os.path.join(d, "absent.json"),
                                          "c" * 40)  # no ledger yet: ok

    def test_good_output_is_fixed(self):
        out = synthetic_output(self.shard, self.digests)
        rec = self.run_with("```json\n" + json.dumps(out) + "\n```")
        self.assertEqual(rec["verdict"], "fixed", rec["problems"])
        self.assertEqual(rec["machine_corrections"], ["stripped-code-fence"])
        self.assertEqual(rec["completeness_check"]["missing_artifact_ids"], [])

    def test_missing_disposition_is_failure(self):
        out = synthetic_output(self.shard, self.digests)
        out["dispositions"].pop()
        rec = self.run_with(json.dumps(out))
        self.assertEqual(rec["verdict"], "review-execution-failure")
        self.assertIn("completeness", rec["problems"])

    def test_digest_drift_is_failure(self):
        out = synthetic_output(self.shard, self.digests)
        out["dispositions"][0]["claim_payload_sha256"] = "0" * 64
        rec = self.run_with(json.dumps(out))
        self.assertTrue(any(p.startswith("digest-not-preserved")
                            for p in rec["problems"]))

    def test_schema_violation_is_failure(self):
        out = synthetic_output(self.shard, self.digests)
        out["dispositions"][0]["reason_codes"] = ["made-up-code"]
        rec = self.run_with(json.dumps(out))
        self.assertIn("schema", rec["problems"])

    def test_prompt_is_control_label_clean_and_bound(self):
        out = synthetic_output(self.shard, self.digests)
        session = FakeSession(json.dumps(out))
        reviewer.review_shard(session, self.template, self.digests,
                              self.shard_path, self.member["artifact_ids"],
                              run_reviewer_a.schema_validator, self.schema)
        self.assertEqual(reviewer.scan_forbidden(session.prompt), [])
        for value in self.digests.values():
            self.assertIn(value, session.prompt)

    def test_real_shard_prompt_carries_verified_schema_bytes(self):
        out = synthetic_output(self.shard, self.digests)
        session = FakeSession(json.dumps(out))
        reviewer.review_shard(session, self.template, self.digests,
                              self.shard_path, self.member["artifact_ids"],
                              run_reviewer_a.schema_validator, self.schema)
        embedded = reviewer.embedded_schema(session.prompt)
        with open(run_reviewer_a.OUTPUT_SCHEMA, "rb") as f:
            file_bytes = f.read()
        self.assertEqual(embedded.encode("utf-8"), file_bytes)
        self.assertEqual(canon.bytes_digest(embedded.encode("utf-8")),
                         self.schema["sha256"])
        self.assertIn(self.schema["sha256"], session.prompt)


if __name__ == "__main__":
    unittest.main()
