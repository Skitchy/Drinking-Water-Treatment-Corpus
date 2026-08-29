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


def shard_record(prompt):
    shard = json.loads(prompt.split("--- BEGIN REVIEW SHARD ---")[1]
                       .split("--- END REVIEW SHARD ---")[0])
    return shard["records"][0]


def disposition(r, rationale="canary record; insufficient evidence"):
    return {
        "artifact_id": r["artifact_id"], "record_sha256": r["record_sha256"],
        "claim_payload_sha256": r["claim_payload_sha256"],
        "normalized_support_anchor_set_sha256":
            r["normalized_support_anchor_set_sha256"],
        "verdict": "reject", "reason_codes": ["insufficient-evidence"],
        "rationale": rationale, "proposed_correction": None}


def conformant(prompt):
    """Build the response a contract-conformant reviewer gives: exactly one
    disposition for the record in the shard, digests preserved."""
    return json.dumps({"dispositions": [disposition(shard_record(prompt))]})


def conformant_id_in_rationale(prompt):
    """Conformant, and the rationale names the artifact ID and the record
    digest in free text: the response that the 2026-08-28 substring rule
    would have failed (discussioncomment-18188318)."""
    r = shard_record(prompt)
    text = (f"Record {r['artifact_id']} (record_sha256 {r['record_sha256']}) "
            f"carries a single canary value; {r['artifact_id']} cannot be "
            "entailed by the supplied source context.")
    return json.dumps({"dispositions": [disposition(r, text)]})


def fenced_conformant(prompt):
    return "```json\n" + conformant(prompt) + "\n```"


def duplicate(prompt):
    r = shard_record(prompt)
    return json.dumps({"dispositions": [disposition(r), disposition(r)]})


def foreign_id(prompt):
    r = dict(shard_record(prompt), artifact_id="f2r-" + "0" * 24)
    return json.dumps({"dispositions": [disposition(r)]})


def digest_mismatch(prompt):
    r = dict(shard_record(prompt), record_sha256="e" * 64)
    return json.dumps({"dispositions": [disposition(r)]})


def extra_foreign(prompt):
    r = shard_record(prompt)
    return json.dumps({"dispositions": [
        disposition(r), disposition(dict(r, artifact_id="f2r-" + "1" * 24))]})


EMPTY = json.dumps({"dispositions": []})
MALFORMED = '{"dispositions": [{"artifact_id": "f2r-'


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

    def test_id_repeated_in_rationale_passes(self):
        records, _ = self.run_probes(conformant_id_in_rationale)
        by_id = {r["id"]: r for r in records}
        self.assertEqual(by_id["allowed-bundle-canary"]["result"], "PASS")
        self.assertEqual(by_id["allowed-bundle-canary"]["check"]["reason"], None)

    def test_fenced_conformant_passes_with_correction_recorded(self):
        records, _ = self.run_probes(fenced_conformant)
        by_id = {r["id"]: r for r in records}
        self.assertEqual(by_id["allowed-bundle-canary"]["result"], "PASS")
        self.assertEqual(by_id["allowed-bundle-canary"]["check"]
                         ["machine_corrections"], ["stripped-code-fence"])

    def test_structural_failures_fail_with_named_reason(self):
        cases = {"malformed-json": MALFORMED, "empty-dispositions": EMPTY,
                 "duplicate-disposition": duplicate,
                 "unexpected-artifact-id": foreign_id,
                 "digest-not-preserved:record_sha256": digest_mismatch,
                 "output-not-object": "[]",
                 "dispositions-not-list": json.dumps({"dispositions": "x"})}
        for reason, first in cases.items():
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(reviewer.ReviewerError,
                                            "allowed-bundle-canary"):
                    self.run_probes(first)
        # a second, foreign disposition beside the correct one is unexpected
        with self.assertRaisesRegex(reviewer.ReviewerError,
                                    "allowed-bundle-canary"):
            self.run_probes(extra_foreign)

    def test_check_canary_disposition_is_typed(self):
        rec = reviewer.probe_canary_record("CANARY-ALLOWED-x")
        good = json.dumps({"dispositions": [disposition(rec)]})
        d = reviewer.check_canary_disposition(good, rec)
        self.assertEqual((d["result"], d["reason"]), ("PASS", None))
        for raw, reason in ((MALFORMED, "malformed-json"),
                            (EMPTY, "empty-dispositions"),
                            (json.dumps({"dispositions": [disposition(rec)] * 2}),
                             "duplicate-disposition"),
                            (json.dumps({"dispositions": [disposition(
                                dict(rec, claim_payload_sha256="f" * 64))]}),
                             "digest-not-preserved:claim_payload_sha256"),
                            (json.dumps({"dispositions": [disposition(
                                dict(rec, artifact_id="f2r-" + "a" * 24))]}),
                             "unexpected-artifact-id"),
                            (json.dumps({"dispositions": [dict(
                                disposition(rec), verdict="maybe")]}),
                             "verdict-not-in-contract")):
            with self.subTest(reason=reason):
                d = reviewer.check_canary_disposition(raw, rec)
                self.assertEqual(d["result"], "FAIL")
                self.assertTrue(d["reason"].startswith(reason), d["reason"])

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

    def test_probe_source_context_is_the_real_projection(self):
        from engine import contract, records, universe
        unit = reviewer.probe_source_unit("CANARY-ALLOWED-x")
        self.assertTrue(contract.validate_source_unit(unit))
        ctx = reviewer.probe_source_context("CANARY-ALLOWED-x")
        # identical key set and rule fields to a real emitted shard's context
        real_keys = set(universe._shard_source_context(unit))
        self.assertEqual(set(ctx), real_keys)
        self.assertEqual(set(ctx["anchor_rules"]),
                         {"selector_scheme", "text_profile", "custody"})
        self.assertEqual(ctx["representation"]["selector"], "probe")
        self.assertNotIn("tree", ctx["representation"])
        # and the probe record's anchor verifies against that unit with the
        # engine's own record verifier, as a real record would
        rec = reviewer.probe_canary_record("CANARY-ALLOWED-x")
        v = records.verify_record(rec, unit)
        self.assertEqual(v["verdict"], "verified", v["problems"])

    def test_forbidden_canary_echo_fails(self):
        def leaky(prompt):
            # a reviewer that saw the ambient CLAUDE.md and echoed it
            with open(os.path.join(self.cwd, "CLAUDE.md")) as f:
                forbidden = f.read().split("\n")[1]
            return conformant(prompt) + forbidden
        with self.assertRaisesRegex(reviewer.ReviewerError,
                                    "forbidden-context-canary"):
            self.run_probes(leaky)


class EvidenceFirst(unittest.TestCase):
    """A check that can fail must persist its evidence before it raises
    (discussioncomment-18197092). These tests fail deliberately and prove
    the evidence survived the exception."""

    def setUp(self):
        self.cwd = tempfile.mkdtemp(prefix="probe-evidence-")
        self.forbidden = os.path.join(self.cwd, "forbidden.txt")
        with open(self.forbidden, "w") as f:
            f.write("the quick brown fox jumps over the lazy dog " * 20)
        self.evidence = os.path.join(self.cwd, "out", "leak-probe-transcript.json")

    def run_probes(self, first):
        session = ProbeSession(first)
        return reviewer.run_leak_probes(session, TEMPLATE, DIGESTS, self.cwd,
                                        self.forbidden,
                                        evidence_path=self.evidence)

    def load(self):
        with open(self.evidence, encoding="utf-8") as f:
            return json.load(f)

    def test_failed_probe_leaves_complete_evidence_before_raise(self):
        with self.assertRaises(reviewer.ReviewerError):
            self.run_probes(EMPTY)
        ev = self.load()
        self.assertEqual(ev["preflight_result"], "FAIL")
        self.assertEqual(ev["failed_probes"], ["allowed-bundle-canary"])
        self.assertIn("allowed-bundle-canary", ev["failure_reason"])
        # raw response, raw prompt, probe record and digests all present
        self.assertEqual(ev["transcripts"][0]["result"]["result"], EMPTY)
        self.assertIn("--- BEGIN REVIEW SHARD ---", ev["transcripts"][0]["prompt"])
        self.assertEqual(ev["probe_record"]["artifact_id"],
                         ev["records"][0]["canary_artifact_id"])
        self.assertEqual(ev["records"][0]["check"]["reason"], "empty-dispositions")
        self.assertEqual(ev["bindings"], DIGESTS)
        self.assertEqual(len(ev["transcripts"][0]["response_sha256"]), 64)
        # and a timestamped sibling that a later run cannot overwrite
        siblings = [n for n in os.listdir(os.path.dirname(self.evidence))
                    if "-FAILED-" in n]
        self.assertEqual(len(siblings), 1)
        with open(os.path.join(os.path.dirname(self.evidence), siblings[0])) as f:
            self.assertEqual(json.load(f)["preflight_result"], "FAIL")

    def test_session_error_is_persisted_before_raise(self):
        class Broken(ProbeSession):
            def run(self, prompt):
                raise reviewer.ReviewerError("session failed after 3 attempts")
        with self.assertRaisesRegex(reviewer.ReviewerError, "session error"):
            reviewer.run_leak_probes(Broken(None), TEMPLATE, DIGESTS, self.cwd,
                                     self.forbidden, evidence_path=self.evidence)
        ev = self.load()
        self.assertEqual(ev["preflight_result"], "FAIL")
        self.assertIn("session failed", ev["session_error"])
        # the prompt was written before the call was attempted
        self.assertEqual(ev["transcripts"][0]["probe_id"], "allowed-bundle-canary")
        self.assertIsNone(ev["transcripts"][0]["result"])

    def test_later_probe_failure_keeps_earlier_evidence(self):
        def leaky(prompt):
            # structurally conformant, but the rationale echoes the ambient
            # CLAUDE.md canary: probe 1 passes, probe 2 fails
            with open(os.path.join(self.cwd, "CLAUDE.md")) as f:
                forbidden = f.read().split("\n")[1]
            return json.dumps({"dispositions": [
                disposition(shard_record(prompt), "seen: " + forbidden)]})
        with self.assertRaises(reviewer.ReviewerError):
            self.run_probes(leaky)
        ev = self.load()
        self.assertEqual(ev["preflight_result"], "FAIL")
        self.assertEqual(ev["failed_probes"], ["forbidden-context-canary"])
        self.assertEqual(ev["records"][0]["result"], "PASS")
        self.assertIn(ev["forbidden_canary"], ev["transcripts"][0]["result"]["result"])

    def test_passing_preflight_is_marked_pass(self):
        records, transcripts = self.run_probes(conformant)
        ev = self.load()
        self.assertEqual(ev["preflight_result"], "PASS")
        self.assertEqual([r["result"] for r in ev["records"]], ["PASS"] * 5)
        self.assertEqual(len(ev["transcripts"]), 2)
        self.assertFalse([n for n in os.listdir(os.path.dirname(self.evidence))
                          if "-FAILED-" in n])

    def test_no_evidence_path_still_raises(self):
        with self.assertRaises(reviewer.ReviewerError):
            reviewer.run_leak_probes(ProbeSession(EMPTY), TEMPLATE, DIGESTS,
                                     self.cwd, self.forbidden)


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
