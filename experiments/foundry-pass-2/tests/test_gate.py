"""Gate tests with synthetic reviewer outputs over the real emitted universe."""

import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PASS2 = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PASS2, "tools"))

from engine import canon, gate  # noqa: E402

OUT = os.path.join(PASS2, "out")
THRESHOLDS = {"coverage_units_min": 30, "acceptance_rate_min": 0.5}


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
        self.units = sorted(set(r["unit_id"] for r in self.review["records"])
                            | {"141.210"})

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write_outputs(self, name, choose):
        d = os.path.join(self.tmp, name)
        os.makedirs(d, exist_ok=True)
        by_unit = {}
        for rec in self.review["records"]:
            by_unit.setdefault(rec["unit_id"], []).append(rec)
        for unit, recs in by_unit.items():
            canon.write_canonical(os.path.join(d, f"shard-{unit}.json"), {
                "dispositions": [disposition(r, choose(r)) for r in recs]})
        return d

    def run_gate(self, choose_a, choose_b, failed_a=(), failed_b=()):
        a = self.write_outputs("a", choose_a)
        b = self.write_outputs("b", choose_b)
        return gate.run_gate(self.tmp, self.review, self.natural, a, b,
                             failed_a, failed_b, self.units, THRESHOLDS)

    def test_all_accept_partitions_and_passes(self):
        report = self.run_gate(lambda r: "accept", lambda r: "accept")
        s = report["decision_summary"]
        self.assertEqual(s["unanimously_accepted_natural"], 387)
        self.assertEqual(s["units_with_at_least_one_accepted_natural_claim"], 37)
        self.assertTrue(report["gates"]["coverage_units_min"]["pass"])
        self.assertTrue(report["gates"]["acceptance_rate_min"]["pass"])
        self.assertEqual(report["partition_counts"]["reconciliation"],
                         "408 = 408 + 0 + 0")

    def test_disagreement_is_excluded_not_resolved(self):
        ids = sorted(r["artifact_id"] for r in self.review["records"])
        half = set(ids[: len(ids) // 2])
        report = self.run_gate(lambda r: "accept",
                               lambda r: "reject" if r["artifact_id"] in half else "accept")
        pc = report["partition_counts"]
        self.assertEqual(pc["excluded_by_reason"]["rejected-by-b"], len(half))
        self.assertEqual(pc["accepted"] + sum(pc["excluded_by_reason"].values()), 408)
        self.assertFalse(report["gates"]["acceptance_rate_min"]["pass"])

    def test_execution_failure_is_its_own_set(self):
        report = self.run_gate(lambda r: "accept", lambda r: "accept",
                               failed_b=["141.131"])
        self.assertEqual(report["partition_counts"]["review_execution_failures"], 20)
        self.assertIn("141.131", report["honest_statistics"]
                      ["review_execution_failures_by_reviewer"]["reviewer_b_units"])

    def test_controls_count_toward_no_gate(self):
        controls = set(self.natural["control_artifact_ids"])
        report = self.run_gate(
            lambda r: "accept",
            lambda r: "accept" if r["artifact_id"] in controls else "reject")
        self.assertEqual(report["decision_summary"]["unanimously_accepted_natural"], 0)
        self.assertEqual(report["partition_counts"]["accepted"], 21)

    def test_class_1_replay(self):
        self.run_gate(lambda r: "accept", lambda r: "reject" if r["unit_id"] == "141.2" else "accept")
        first = {n: canon.file_sha256(os.path.join(self.tmp, "gate", n))
                 for n in os.listdir(os.path.join(self.tmp, "gate"))}
        self.run_gate(lambda r: "accept", lambda r: "reject" if r["unit_id"] == "141.2" else "accept")
        second = {n: canon.file_sha256(os.path.join(self.tmp, "gate", n))
                  for n in os.listdir(os.path.join(self.tmp, "gate"))}
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
