"""Gate tests with schema-valid synthetic reviewer outputs over the real
emitted universe, validated by Ari's own validator. Includes the two cases
from Ari's 2026-08-27 review: issuance with control grading pending, and
unvalidated inputs."""

import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PASS2 = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PASS2, "tools"))

from engine import canon, gate  # noqa: E402
from run_reviewer_a import schema_validator, bundle_digests  # noqa: E402

OUT = os.path.join(PASS2, os.environ.get("FOUNDRY_PASS2_OUT", "out"))  # CI: out-fixture
THRESHOLDS = {"coverage_units_min": 30, "acceptance_rate_min": 0.5}
GRADING_PASS = {"hard_gate_result": "PASS", "metrics": {}}


EXPECTED = {"system_prompt_sha256": "1" * 64, "output_schema_sha256": "2" * 64}


def run_manifest(tmp, role):
    """A minimal valid run-record manifest with real files behind it."""
    base = os.path.join(tmp, "run-" + role)
    os.makedirs(base, exist_ok=True)
    members = []
    for kind, name in (("leak-probe-transcript", "probe.json"),
                       ("identity", "identity.json"),
                       ("run-record", "rr-1.json")):
        path = os.path.join(base, name)
        canon.write_canonical(path, {"kind": kind})
        members.append({"kind": kind, "path": name,
                        "sha256": canon.file_sha256(path)})
    return {"members": members}, base


def identity(role):
    ident = {f: "e" * 64 for f in gate.IDENTITY_REQUIRED_FIELDS}
    ident.update({f: "x" for f in ("reviewer_role", "operator_lineage",
                                   "model_provider", "model_id",
                                   "model_version_or_build")})
    ident.update(EXPECTED)
    ident.update({"reviewer_role": role, "bound_before_first_real_review": True,
                  "leak_probes": [{"id": p, "pass": True} for p in (
                      "allowed-bundle-canary", "forbidden-context-canary",
                      "forbidden-access", "history-root", "control-label-scan")]})
    return ident


def disposition(rec, verdict):
    return {"artifact_id": rec["artifact_id"],
            "record_sha256": rec["record_sha256"],
            "claim_payload_sha256": rec["claim_payload_sha256"],
            "normalized_support_anchor_set_sha256":
                rec["normalized_support_anchor_set_sha256"],
            "verdict": verdict, "rationale": "synthetic",
            "reason_codes": [] if verdict == "accept" else ["other-material-error"],
            "proposed_correction": None}


class GateOverRealUniverse(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.review = canon.load_json(os.path.join(OUT, "review-universe.json"))
        self.natural = canon.load_json(
            os.path.join(OUT, "sealed", "natural-universe.json"))
        self.manifest = canon.load_json(os.path.join(OUT, "shard-manifest.json"))
        self.units = sorted(set(r["unit_id"] for r in self.review["records"])
                            | {"141.210"})
        d = bundle_digests()
        self.bindings = {
            "contract_sha256": d["CONTRACT_SHA256"],
            "review_input_bundle_sha256": d["REVIEW_INPUT_BUNDLE_SHA256"],
            "shard_manifest_sha256": d["SHARD_MANIFEST_SHA256"],
            "reviewer_a_identity_sha256": "a" * 64,
            "reviewer_b_identity_sha256": "b" * 64,
        }
        self.by_id = {r["artifact_id"]: r for r in self.review["records"]}

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write_outputs(self, name, choose, identity_sha, drop_shard=None,
                      corrupt=None):
        d = os.path.join(self.tmp, name)
        os.makedirs(d, exist_ok=True)
        for member in self.manifest["shards"]:
            if member["shard_id"] == drop_shard:
                continue
            recs = [self.by_id[i] for i in member["artifact_ids"]]
            dispositions = [disposition(r, choose(r)) for r in recs]
            output = {
                "artifact_version": "foundry-pass-2-review-output/experimental-v0.1",
                "contract_sha256": self.bindings["contract_sha256"],
                "review_input_bundle_sha256": self.bindings["review_input_bundle_sha256"],
                "shard_manifest_sha256": self.bindings["shard_manifest_sha256"],
                "reviewer_identity_sha256": identity_sha,
                "shard_id": member["shard_id"],
                "dispositions": dispositions,
                "completeness": {"input_artifact_count": len(recs),
                                 "output_disposition_count": len(dispositions),
                                 "duplicate_artifact_ids": [], "missing_artifact_ids": [],
                                 "unexpected_artifact_ids": []},
            }
            if corrupt and member["shard_id"] == corrupt:
                output["dispositions"][0]["reason_codes"] = ["not-a-code"]
            canon.write_canonical(os.path.join(d, member["shard_id"] + ".json"), output)
        return d

    def run_gate(self, choose_a, choose_b, identity_b=identity("reviewer_b"),
                 grading=GRADING_PASS, **kw):
        a = self.write_outputs("a", choose_a, "a" * 64)
        b = self.write_outputs("b", choose_b, "b" * 64, **kw)
        ma, base_a = run_manifest(self.tmp, "a")
        mb, base_b = run_manifest(self.tmp, "b")
        return gate.run_gate(self.tmp, self.review, self.natural, self.manifest,
                             self.bindings, a, b, identity("reviewer_a"),
                             identity_b, EXPECTED, EXPECTED, ma, mb, base_a,
                             base_b, grading, [], [], self.units,
                             THRESHOLDS, schema_validator)

    def statuses(self, report):
        return {k: v["status"] for k, v in report["gates"].items()}

    def test_all_accept_passes_every_in_report_gate(self):
        report = self.run_gate(lambda r: "accept", lambda r: "accept")
        s = report["decision_summary"]
        self.assertEqual(s["unanimously_accepted_natural"], 387)
        self.assertEqual(s["units_with_at_least_one_accepted_natural_claim"], 37)
        self.assertEqual(report["partition_counts"]["reconciliation"], "408 = 408 + 0 + 0")
        self.assertTrue(report["issuance"]["all_in_report_gates_pass"])
        self.assertEqual(report["issuance"]["not_pass"], ["class_1_replay"])

    def test_pending_control_grading_blocks_issuance(self):
        """Ari's exercise: all-accept outputs with grading absent."""
        report = self.run_gate(lambda r: "accept", lambda r: "accept", grading=None)
        self.assertEqual(self.statuses(report)["control_grading"], "MISSING")
        self.assertFalse(report["issuance"]["all_in_report_gates_pass"])
        sha, issued = gate.release_manifest(
            self.tmp, {"x": {"path": "p", "sha256": "s"}}, report, gate.status("PASS"))
        self.assertFalse(issued)

    def test_failed_grading_blocks_issuance(self):
        report = self.run_gate(lambda r: "accept", lambda r: "accept",
                               grading={"hard_gate_result": "FAIL"})
        self.assertEqual(self.statuses(report)["control_grading"], "FAIL")
        self.assertFalse(report["issuance"]["all_in_report_gates_pass"])

    def test_missing_reviewer_b_identity_blocks_issuance(self):
        report = self.run_gate(lambda r: "accept", lambda r: "accept", identity_b=None)
        self.assertEqual(self.statuses(report)["reviewer_b_identity"], "MISSING")
        self.assertFalse(report["issuance"]["all_in_report_gates_pass"])

    def test_failed_leak_probe_fails_identity_gate(self):
        bad = identity("reviewer_b")
        bad["leak_probes"][2]["pass"] = False
        report = self.run_gate(lambda r: "accept", lambda r: "accept", identity_b=bad)
        self.assertEqual(self.statuses(report)["reviewer_b_identity"], "FAIL")

    def test_bogus_digests_fail_identity_gate(self):
        """Ari's exercise: every digest field set to the literal 'bogus'."""
        bad = identity("reviewer_b")
        for f in gate.IDENTITY_REQUIRED_FIELDS:
            if f.endswith("_sha256"):
                bad[f] = "bogus"
        report = self.run_gate(lambda r: "accept", lambda r: "accept", identity_b=bad)
        g = report["gates"]["reviewer_b_identity"]
        self.assertEqual(g["status"], "FAIL")
        self.assertTrue(any("not a sha256" in p for p in g["problems"]))

    def test_self_asserted_digest_that_mismatches_bound_artifact_fails(self):
        bad = identity("reviewer_b")
        bad["system_prompt_sha256"] = "f" * 64  # well-formed, wrong
        report = self.run_gate(lambda r: "accept", lambda r: "accept", identity_b=bad)
        g = report["gates"]["reviewer_b_identity"]
        self.assertEqual(g["status"], "FAIL")
        self.assertIn("system_prompt_sha256 does not match bound artifact", g["problems"])

    def test_run_record_manifest_missing_or_tampered_fails(self):
        report = self.run_gate(lambda r: "accept", lambda r: "accept")
        self.assertEqual(report["gates"]["reviewer_a_run_record"]["status"], "PASS")
        ma, base_a = run_manifest(self.tmp, "t")
        ma["members"][0]["sha256"] = "0" * 64
        self.assertEqual(gate.check_run_record_manifest(ma, base_a)["status"], "FAIL")
        self.assertEqual(gate.check_run_record_manifest(None, base_a)["status"], "MISSING")

    def test_replay_fail_blocks_issuance_in_manifest(self):
        report = self.run_gate(lambda r: "accept", lambda r: "accept")
        _, issued = gate.release_manifest(
            self.tmp, {"x": {"path": "p", "sha256": "s"}}, report, gate.status("FAIL"))
        self.assertFalse(issued)
        _, issued = gate.release_manifest(
            self.tmp, {"x": {"path": "p", "sha256": "s"}}, report, gate.status("PASS"))
        self.assertTrue(issued)

    def test_schema_invalid_output_fails_validity_and_unit(self):
        report = self.run_gate(lambda r: "accept", lambda r: "accept",
                               corrupt="shard-141.131")
        self.assertEqual(self.statuses(report)["reviewer_output_validity"], "FAIL")
        self.assertIn("141.131", report["honest_statistics"]
                      ["review_execution_failures_by_reviewer"]["reviewer_b_units"])
        # every record in the corrupted shard fails execution; the count is
        # whatever the mixed universe put there, never a hardcoded number
        expected = next(m["record_count"] for m in self.manifest["shards"]
                        if m["shard_id"] == "shard-141.131")
        self.assertEqual(report["partition_counts"]["review_execution_failures"], expected)

    def test_missing_shard_output_is_execution_failure(self):
        report = self.run_gate(lambda r: "accept", lambda r: "accept",
                               drop_shard="shard-141.2")
        self.assertEqual(self.statuses(report)["reviewer_output_validity"], "FAIL")
        self.assertGreater(report["partition_counts"]["review_execution_failures"], 0)

    def test_wrong_identity_binding_rejects_file(self):
        a = self.write_outputs("a", lambda r: "accept", "a" * 64)
        b = self.write_outputs("b", lambda r: "accept", "0" * 64)  # wrong identity
        ma, base_a = run_manifest(self.tmp, "a")
        mb, base_b = run_manifest(self.tmp, "b")
        report = gate.run_gate(self.tmp, self.review, self.natural, self.manifest,
                               self.bindings, a, b, identity("reviewer_a"),
                               identity("reviewer_b"), EXPECTED, EXPECTED, ma, mb,
                               base_a, base_b, GRADING_PASS, [], [],
                               self.units, THRESHOLDS, schema_validator)
        self.assertEqual(self.statuses(report)["reviewer_output_validity"], "FAIL")
        self.assertEqual(report["partition_counts"]["accepted"], 0)

    def test_disagreement_is_excluded_not_resolved(self):
        ids = sorted(self.by_id)
        half = set(ids[: len(ids) // 2])
        report = self.run_gate(lambda r: "accept",
                               lambda r: "reject" if r["artifact_id"] in half else "accept")
        pc = report["partition_counts"]
        self.assertEqual(pc["excluded_by_reason"]["rejected-by-b"], len(half))
        self.assertEqual(self.statuses(report)["acceptance_rate_min"], "FAIL")

    def test_controls_count_toward_no_gate(self):
        controls = set(self.natural["control_artifact_ids"])
        report = self.run_gate(
            lambda r: "accept",
            lambda r: "accept" if r["artifact_id"] in controls else "reject")
        self.assertEqual(report["decision_summary"]["unanimously_accepted_natural"], 0)
        self.assertEqual(report["partition_counts"]["accepted"], 21)

    def test_class_1_replay(self):
        choose_b = lambda r: "reject" if r["unit_id"] == "141.2" else "accept"  # noqa: E731
        self.run_gate(lambda r: "accept", choose_b)
        first = {n: canon.file_sha256(os.path.join(self.tmp, "gate", n))
                 for n in os.listdir(os.path.join(self.tmp, "gate"))}
        self.run_gate(lambda r: "accept", choose_b)
        second = {n: canon.file_sha256(os.path.join(self.tmp, "gate", n))
                  for n in os.listdir(os.path.join(self.tmp, "gate"))}
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
