"""Regression tests for Ari's v0.1.1 public bundle verifier."""

import importlib.util
import os
import unittest


PASS2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFIER = os.path.join(
    PASS2,
    "evaluator",
    "ari",
    "verify-ari-evaluator-bundle-v0.1.2.py",
)

spec = importlib.util.spec_from_file_location("ari_verifier_v0_1_2", VERIFIER)
ari_verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ari_verifier)


class RecursiveForbiddenKeyScan(unittest.TestCase):
    def test_forbidden_key_inside_records_array_fails(self):
        mutated = {
            "count": 1,
            "records": [
                {
                    "evidence": [
                        {
                            "support_anchor": {
                                "truth_label": "must remain sealed"
                            }
                        }
                    ]
                }
            ],
        }
        with self.assertRaisesRegex(SystemExit, "truth_label"):
            ari_verifier.verify_no_forbidden_control_keys(mutated)

    def test_clean_nested_records_pass(self):
        clean = {
            "count": 1,
            "records": [
                {
                    "evidence": [
                        {"support_anchor": {"capture_sha256": "a" * 64}}
                    ]
                }
            ],
        }
        ari_verifier.verify_no_forbidden_control_keys(clean)

    def test_truth_string_inside_records_array_fails(self):
        mutated = {
            "count": 1,
            "records": [{"notes": ["deliberately-wrong"]}],
        }
        with self.assertRaisesRegex(SystemExit, "truth or stratum"):
            ari_verifier.verify_no_forbidden_control_keys(mutated)


if __name__ == "__main__":
    unittest.main()
