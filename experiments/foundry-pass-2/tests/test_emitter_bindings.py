"""The emitter binds only Ari's v0.2 packet and refuses the burned v0.1
controls, any default, and any controls file whose bytes do not match the
public commitment. The public binding check must pass on the committed bundle."""

import os
import sys
import tempfile
import unittest

PASS2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PASS2)
sys.path.insert(0, os.path.join(PASS2, "tools"))

import emit_bundle  # noqa: E402
import check_bundle_bindings  # noqa: E402

ARI = os.path.join(PASS2, "evaluator", "ari")


class EmitterBindings(unittest.TestCase):
    def test_no_default_controls(self):
        with self.assertRaisesRegex(SystemExit, "--controls PATH is required"):
            emit_bundle.resolve_controls(["emit_bundle.py"])

    def test_controls_inside_repo_refused(self):
        burned = os.path.join(ARI, "control-records-v0.1.json")
        with self.assertRaisesRegex(SystemExit, "outside the repository"):
            emit_bundle.resolve_controls(["emit_bundle.py", "--controls", burned])

    def test_mismatched_controls_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            bogus = os.path.join(tmp, "controls.json")
            with open(bogus, "w") as f:
                f.write('{"records":[]}\n')
            with self.assertRaisesRegex(SystemExit, "does not match the committed"):
                emit_bundle.main(["emit_bundle.py", "--controls", bogus])

    def test_public_bindings_recompute(self):
        b = emit_bundle.public_bindings()
        self.assertEqual(b["brief"]["sha256"], emit_bundle.PROPOSED["brief_sha256"])
        self.assertEqual(b["evaluator_manifest"]["sha256"],
                         emit_bundle.PROPOSED["evaluator_manifest_sha256"])
        self.assertEqual(b["control_records_bundle"]["byte_length"], 43688)
        self.assertEqual(b["sealed_oracle"]["byte_length"], 27615)
        self.assertTrue(all(v.endswith("-v0.2.json") or "v0.1.1" in v
                            for k, v in emit_bundle.PUBLIC_MEMBERS.items()
                            if k in ("evaluator_manifest", "reviewer_contract",
                                     "mixed_control_commitment",
                                     "public_bundle_verifier")))

    def test_committed_bundle_bindings_pass(self):
        self.assertEqual(check_bundle_bindings.check()["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
