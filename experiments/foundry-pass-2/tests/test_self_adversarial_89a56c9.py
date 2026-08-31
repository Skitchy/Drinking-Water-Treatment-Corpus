"""Self-adversarial pass on integration head 89a56c9 (2026-08-31): four
holes found by attacking the qualify path, each reproduced here as the
failing case it was, then held closed by the fix.

1. PASS evidence was destroyed by the next attempt (only FAIL attempts got a
   content-addressed sibling; the fdcd340 PASS transcript 78d880e8 no longer
   exists on disk).
2. A non-ReviewerError raised after a model call escaped qualify() with no
   ledger line, leaving the head re-attemptable.
3. render_task substituted placeholders sequentially, so shard data
   containing a placeholder token was rewritten in the reviewer's copy and
   legitimate `{{` in data hard-stopped the run.
4. IsolatedSession retried the CLI up to three times invisibly; evidence and
   ledger reported one call.

Every test writes only under temp directories.
"""

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

FIXTURE = os.environ.get("FOUNDRY_PASS2_OUT", os.path.join(PASS2, "out-fixture"))
FIXTURE_READY = os.path.isfile(os.path.join(FIXTURE, "review-input-bundle.json"))


def _template_and_schema():
    return (run_reviewer_a.load_template(FIXTURE),
            run_reviewer_a.load_schema(FIXTURE))


DIGESTS = {"CONTRACT_SHA256": "c" * 64, "REVIEW_INPUT_BUNDLE_SHA256": "b" * 64,
           "SHARD_MANIFEST_SHA256": "1" * 64, "REVIEWER_IDENTITY_SHA256": "0" * 64}


class ConformantSession:
    """Answers the canary probe with a complete, schema-valid disposition
    built from the probe record it was shown; refuses the access probe."""
    model = "fake"

    def __init__(self):
        self.calls = 0

    def run(self, prompt):
        self.calls += 1
        if self.calls == 1:
            shard = json.loads(prompt.split(reviewer.SHARD_SEPARATOR)[1]
                               .split("--- END REVIEW SHARD ---")[0])
            r = shard["records"][0]
            # echo the bindings the prompt actually carries, as a real
            # conformant reviewer would
            def header(label):
                return re.search(label + r": `([0-9a-f]{64})`", prompt).group(1)
            body = json.dumps({
                "artifact_version": "foundry-pass-2-reviewer-output/experimental-v0.1",
                "contract_sha256": header("Contract SHA-256"),
                "review_input_bundle_sha256": header("Review-input bundle SHA-256"),
                "shard_manifest_sha256": header("Shard manifest SHA-256"),
                "reviewer_identity_sha256": header("Reviewer identity SHA-256"),
                "shard_id": "probe",
                "dispositions": [{
                    "artifact_id": r["artifact_id"],
                    "record_sha256": r["record_sha256"],
                    "claim_payload_sha256": r["claim_payload_sha256"],
                    "normalized_support_anchor_set_sha256":
                        r["normalized_support_anchor_set_sha256"],
                    "verdict": "reject", "reason_codes": ["insufficient-evidence"],
                    "rationale": "canary record", "proposed_correction": None}],
            })
        else:
            body = "I cannot access files."
        return {"result": body, "session_id": f"fake-{self.calls}", "num_turns": 1}


def _accept(output):
    return True, {"validator": "test-accept"}


@unittest.skipUnless(FIXTURE_READY, "public fixture not emitted")
class Hole1PassEvidenceSurvives(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="sa-hole1-")
        self.evidence = os.path.join(self.dir, "leak-probe-transcript.json")
        self.template, self.schema = _template_and_schema()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def _run(self, session):
        return reviewer.run_leak_probes(
            session, self.template, DIGESTS, self.dir,
            os.path.join(PASS2, "README.md"), evidence_path=self.evidence,
            schema=self.schema, schema_validator=_accept)

    def test_pass_gets_content_addressed_sibling_and_manifest(self):
        self._run(ConformantSession())
        working = canon.load_json(self.evidence)
        self.assertEqual(working["preflight_result"], "PASS")
        digest = canon.file_sha256(self.evidence)
        sibling = os.path.join(self.dir, f"leak-probe-transcript-PASSED-{digest}.json")
        self.assertTrue(os.path.isfile(sibling))
        self.assertEqual(canon.file_sha256(sibling), digest)
        manifest = canon.load_json(os.path.join(
            self.dir, reviewer.PASSED_PREFLIGHT_MANIFEST))
        self.assertEqual([m["sha256"] for m in manifest["members"]], [digest])
        self.assertEqual(manifest["members"][0]["preflight_result"], "PASS")

    def test_later_fail_attempt_cannot_destroy_pass_evidence(self):
        self._run(ConformantSession())
        pass_digest = canon.file_sha256(self.evidence)
        with open(self.evidence, "rb") as f:
            pass_bytes = f.read()
        # second attempt in the same directory fails at the canary
        class Broken(ConformantSession):
            def run(self, prompt):
                self.calls += 1
                return {"result": "not json", "session_id": "x", "num_turns": 1}
        with self.assertRaises(reviewer.ReviewerError):
            self._run(Broken())
        # the working file now holds the FAIL attempt (this is the old hole)
        self.assertEqual(canon.load_json(self.evidence)["preflight_result"], "FAIL")
        self.assertNotEqual(canon.file_sha256(self.evidence), pass_digest)
        # the PASS bytes are still on disk, byte-identical, under their digest
        sibling = os.path.join(self.dir, f"leak-probe-transcript-PASSED-{pass_digest}.json")
        with open(sibling, "rb") as f:
            self.assertEqual(f.read(), pass_bytes)
        # and the FAIL attempt got its own sibling as before
        self.assertTrue(any("-FAILED-" in n for n in os.listdir(self.dir)))


@unittest.skipUnless(FIXTURE_READY, "public fixture not emitted")
class Hole2SpentCallIsAlwaysLedgered(unittest.TestCase):
    """qualify() with a validator that raises a plain RuntimeError after the
    model call (a missing `node` binary would do this in production)."""

    def setUp(self):
        self.q = tempfile.mkdtemp(prefix="sa-hole2-")
        self.saved = {k: getattr(run_reviewer_a, k) for k in
                      ("Q_OUT", "git_head", "make_session", "schema_validator",
                       "FIXTURE_OUT", "MODEL", "cli_version")}
        run_reviewer_a.Q_OUT = self.q
        run_reviewer_a.FIXTURE_OUT = FIXTURE
        run_reviewer_a.MODEL = "fake"
        run_reviewer_a.git_head = lambda: ("a" * 40, True)
        # CI runners carry no `claude` binary (run 33389234939 went red on
        # exactly this); the build string is an input identity, stubbed here
        run_reviewer_a.cli_version = lambda: "fake-cli"

        self.sessions = []

        def make(system_prompt, cwd):
            s = ConformantSession()
            self.sessions.append(s)
            return s
        run_reviewer_a.make_session = make

        def exploding(output):
            raise RuntimeError("node: command not found")
        run_reviewer_a.schema_validator = exploding

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(run_reviewer_a, k, v)
        shutil.rmtree(self.q)

    def test_harness_error_after_call_is_ledgered_and_head_refused(self):
        with self.assertRaises(SystemExit) as ctx:
            run_reviewer_a.qualify()
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(self.sessions[0].calls, 1)
        ledger = canon.load_json(os.path.join(self.q, "qualification-ledger.json"))
        self.assertEqual(len(ledger["attempts"]), 1)
        entry = ledger["attempts"][0]
        self.assertEqual(entry["result"], "FAIL")
        self.assertEqual(entry["head"], "a" * 40)
        self.assertEqual(entry["model_calls"], 1)
        self.assertEqual(entry["cli_invocations"], 1)
        # evidence names the content-addressed sibling, which exists
        self.assertIn("-FAILED-", entry["evidence_path"])
        self.assertTrue(os.path.isfile(os.path.join(self.q, entry["evidence_path"])))
        self.assertEqual(canon.file_sha256(os.path.join(self.q, entry["evidence_path"])),
                         entry["evidence_sha256"])
        persisted = canon.load_json(os.path.join(self.q, entry["evidence_path"]))
        self.assertEqual(persisted["preflight_result"], "FAIL")
        self.assertIn("RuntimeError", persisted["failure_reason"])
        # a second run on the same head is refused BEFORE any session exists
        with self.assertRaises(SystemExit) as ctx2:
            run_reviewer_a.qualify()
        self.assertIn("already has 1 ledgered attempt", str(ctx2.exception))
        self.assertEqual(len(self.sessions), 1)

    def test_pass_ledger_line_names_passed_sibling(self):
        run_reviewer_a.schema_validator = _accept
        with self.assertRaises(SystemExit) as ctx:
            run_reviewer_a.qualify()
        self.assertEqual(ctx.exception.code, 0)
        entry = canon.load_json(os.path.join(
            self.q, "qualification-ledger.json"))["attempts"][0]
        self.assertEqual(entry["result"], "PASS")
        self.assertIn("-PASSED-", entry["evidence_path"])
        self.assertEqual(canon.file_sha256(os.path.join(self.q, entry["evidence_path"])),
                         entry["evidence_sha256"])


@unittest.skipUnless(FIXTURE_READY, "public fixture not emitted")
class Hole3TemplateRenderingIsSinglePass(unittest.TestCase):
    def setUp(self):
        self.template, self.schema = _template_and_schema()

    def _shard_body(self, prompt):
        return (prompt.split(reviewer.SHARD_SEPARATOR)[1]
                .split("--- END REVIEW SHARD ---")[0].strip())

    def test_placeholder_token_inside_shard_data_is_carried_verbatim(self):
        shard_json = json.dumps({"shard_id": "x", "records": [],
                                 "quote": "text says {{CONTRACT_SHA256}} here"})
        prompt = reviewer.render_review_prompt(self.template, "x", shard_json,
                                               DIGESTS, self.schema)
        self.assertEqual(self._shard_body(prompt), shard_json)
        self.assertEqual(prompt.count("c" * 64), 1)  # the header binding only

    def test_legitimate_braces_in_data_do_not_hard_stop(self):
        shard_json = json.dumps({"shard_id": "x", "records": [],
                                 "quote": "template doc: {{ user.name }} and {{X}}"})
        prompt = reviewer.render_review_prompt(self.template, "x", shard_json,
                                               DIGESTS, self.schema)
        self.assertEqual(self._shard_body(prompt), shard_json)

    def test_unrendered_template_placeholder_still_hard_stops(self):
        with self.assertRaises(reviewer.ReviewerError) as ctx:
            reviewer.render_task("a {{SHARD_ID}} b {{NOT_SUPPLIED}}", SHARD_ID="s")
        self.assertIn("NOT_SUPPLIED", str(ctx.exception))

    def test_schema_bytes_and_bindings_unchanged_by_the_rewrite(self):
        shard_json = json.dumps({"shard_id": "x", "records": []})
        prompt = reviewer.render_review_prompt(self.template, "x", shard_json,
                                               DIGESTS, self.schema)
        self.assertEqual(reviewer.embedded_schema(prompt), self.schema["json"])
        for value in DIGESTS.values():
            self.assertIn(value, prompt)


class Hole4CliInvocationsAreCounted(unittest.TestCase):
    """A fake `claude` on PATH fails twice then succeeds; the session must
    report three invocations for one logical call."""

    def setUp(self):
        self.bin = tempfile.mkdtemp(prefix="sa-hole4-bin-")
        self.cwd = tempfile.mkdtemp(prefix="sa-hole4-cwd-")
        self.counter = os.path.join(self.bin, "count")
        fake = os.path.join(self.bin, "claude")
        with open(fake, "w") as f:
            f.write("#!/bin/sh\n"
                    f"n=$(cat {self.counter} 2>/dev/null || echo 0); n=$((n+1)); "
                    f"echo $n > {self.counter}\n"
                    "cat >/dev/null\n"
                    "if [ $n -lt 3 ]; then echo 'api error' >&2; exit 1; fi\n"
                    "printf '%s' '{\"result\":\"{}\",\"session_id\":\"s\","
                    "\"num_turns\":1}'\n")
        os.chmod(fake, 0o755)
        self.path = os.environ["PATH"]
        os.environ["PATH"] = self.bin + os.pathsep + self.path
        self.sleep = reviewer.time.sleep
        reviewer.time.sleep = lambda s: None

    def tearDown(self):
        os.environ["PATH"] = self.path
        reviewer.time.sleep = self.sleep
        shutil.rmtree(self.bin)
        shutil.rmtree(self.cwd)

    def test_retries_are_visible_on_the_session(self):
        session = reviewer.IsolatedSession("fake", "sys", self.cwd)
        out = session.run("prompt")
        self.assertEqual(out["result"], "{}")
        with open(self.counter) as f:
            self.assertEqual(f.read().strip(), "3")
        accounting = reviewer.invocation_accounting(session)
        self.assertEqual(accounting["cli_invocations"], 3)
        self.assertEqual([e["invocation"] for e in accounting["cli_invocation_log"]],
                         [1, 2, 3])
        self.assertTrue(accounting["cli_invocation_log"][0]["outcome"].startswith("rc=1"))
        self.assertEqual(accounting["cli_invocation_log"][2]["outcome"], "rc=0")

    def test_exhausted_retries_are_visible_before_the_hard_stop(self):
        session = reviewer.IsolatedSession("fake", "sys", self.cwd, attempts=2)
        with self.assertRaises(reviewer.ReviewerError):
            session.run("prompt")
        self.assertEqual(reviewer.invocation_accounting(session)["cli_invocations"], 2)

    def test_fake_sessions_default_to_one(self):
        self.assertEqual(reviewer.invocation_accounting(object())["cli_invocations"], 1)


if __name__ == "__main__":
    unittest.main()
