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

OUT = os.path.join(PASS2, os.environ.get("FOUNDRY_PASS2_OUT", "out"))  # CI: out-fixture


class FakeSession:
    model = "fake"

    def __init__(self, response):
        self.response = response

    def run(self, prompt):
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

    def run_with(self, response):
        session = FakeSession(response)
        return reviewer.review_shard(
            session, self.template, self.digests, self.shard_path,
            self.member["artifact_ids"], run_reviewer_a.schema_validator)

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
                              run_reviewer_a.schema_validator)
        self.assertEqual(reviewer.scan_forbidden(session.prompt), [])
        for value in self.digests.values():
            self.assertIn(value, session.prompt)


if __name__ == "__main__":
    unittest.main()
