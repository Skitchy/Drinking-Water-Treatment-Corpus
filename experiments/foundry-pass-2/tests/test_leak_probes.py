"""Leak probes, offline. The allowed-bundle-canary probe must pass on a
contract-conformant response (one disposition for the probe record, digests
preserved) and FAIL on the empty-dispositions response a conformant reviewer
returned to the 2026-08-27 instruction-in-data probe (discussioncomment-18187871)."""

import json
import os
import sys
import tempfile
import unittest

PASS2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PASS2)

from engine import reviewer  # noqa: E402

TEMPLATE = open(os.path.join(PASS2, "evaluator", "ari",
                             "reviewer-task-template-v0.1.md"),
                encoding="utf-8").read()
DIGESTS = {"CONTRACT_SHA256": "c" * 64, "REVIEW_INPUT_BUNDLE_SHA256": "b" * 64,
           "SHARD_MANIFEST_SHA256": "m" * 64, "REVIEWER_IDENTITY_SHA256": "0" * 64}


class ProbeSession:
    """Answers the first (canary) call with `first`, later calls with a
    benign refusal; distinct session ids, one turn each."""
    model = "fake"

    def __init__(self, first):
        self.first = first
        self.calls = 0

    def run(self, prompt):
        self.calls += 1
        self.prompt = prompt
        if self.calls == 1:
            self.first_prompt = prompt
            body = self.first(prompt) if callable(self.first) else self.first
        else:
            body = "I cannot access files."
        return {"result": body, "session_id": f"fake-{self.calls}",
                "num_turns": 1}


def conformant(prompt):
    """Build the response a contract-conformant reviewer gives: exactly one
    disposition for the record in the shard, digests preserved."""
    shard = json.loads(prompt.split("--- BEGIN REVIEW SHARD ---")[1]
                       .split("--- END REVIEW SHARD ---")[0])
    r = shard["records"][0]
    return json.dumps({"dispositions": [{
        "artifact_id": r["artifact_id"], "record_sha256": r["record_sha256"],
        "claim_payload_sha256": r["claim_payload_sha256"],
        "normalized_support_anchor_set_sha256":
            r["normalized_support_anchor_set_sha256"],
        "verdict": "reject", "reason_codes": ["insufficient-evidence"]}]})


EMPTY = json.dumps({"dispositions": []})


class LeakProbes(unittest.TestCase):
    def setUp(self):
        self.cwd = tempfile.mkdtemp(prefix="probe-test-")
        self.forbidden = os.path.join(self.cwd, "forbidden.txt")
        with open(self.forbidden, "w") as f:
            f.write("the quick brown fox jumps over the lazy dog " * 20)

    def run_probes(self, first):
        session = ProbeSession(first)
        return reviewer.run_leak_probes(session, TEMPLATE, DIGESTS,
                                        self.cwd, self.forbidden)

    def test_conformant_response_passes(self):
        records, transcripts = self.run_probes(conformant)
        by_id = {r["id"]: r for r in records}
        self.assertTrue(by_id["allowed-bundle-canary"]["pass"])
        self.assertTrue(by_id["forbidden-context-canary"]["pass"])
        self.assertTrue(by_id["forbidden-access"]["pass"])
        self.assertTrue(by_id["history-root"]["pass"])
        self.assertEqual(len(transcripts), 2)

    def test_empty_dispositions_fails_allowed_canary(self):
        with self.assertRaisesRegex(reviewer.ReviewerError,
                                    "allowed-bundle-canary"):
            self.run_probes(EMPTY)

    def test_probe_shard_is_real_shaped_and_clean(self):
        session = ProbeSession(conformant)
        reviewer.run_leak_probes(session, TEMPLATE, DIGESTS, self.cwd,
                                 self.forbidden)
        # the first prompt carried a one-record shard whose record id derives
        # from the canary and whose bytes hold no control-label terms
        first_prompt = session.first_prompt
        self.assertNotIn("instruction", first_prompt)
        self.assertIn("CANARY-ALLOWED-", first_prompt)
        rec = reviewer.probe_canary_record("CANARY-ALLOWED-x")
        self.assertEqual(rec["artifact_id"], "f2r-" + rec["record_sha256"][:24])
        self.assertEqual(reviewer.scan_forbidden(json.dumps(rec)), [])

    def test_forbidden_canary_echo_fails(self):
        def leaky(prompt):
            # a reviewer that saw the ambient CLAUDE.md and echoed it
            with open(os.path.join(self.cwd, "CLAUDE.md")) as f:
                forbidden = f.read().split("\n")[1]
            return conformant(prompt) + forbidden
        with self.assertRaisesRegex(reviewer.ReviewerError,
                                    "forbidden-context-canary"):
            self.run_probes(leaky)


class SessionCommand(unittest.TestCase):
    def test_isolation_trio_and_no_persistence(self):
        cmd = reviewer.IsolatedSession("m", "sp", "/tmp").command()
        for flag in ("--disallowedTools", "--strict-mcp-config",
                     "--setting-sources", "--no-session-persistence"):
            self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index("--setting-sources") + 1], "")
        limits = reviewer.IsolatedSession("m", "sp", "/tmp") \
            .environment_boundary()["honest_limits"]
        self.assertTrue(any("haiku" in l for l in limits))


if __name__ == "__main__":
    unittest.main()
