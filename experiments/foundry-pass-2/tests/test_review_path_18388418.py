"""Ari's five review-path findings on 0466557 (maintainer authorization
discussioncomment-18388418, 2026-09-10), each reproduced here by execution
in an isolated temporary root. Every test in this module FAILED against
0466557 before the fix (the reproduction) and fails closed after it,
except the two controls that must hold on both heads: a governed root
still passes the store check, and the claim's reservation pin (already
held at 0466557) is now required rather than optional.

1. refuse loud on every foreign or orphaned evidence artifact: unknown root
   entries, unknown or malformed claim artifacts, artifacts for shard IDs
   the bound manifest does not name, and content-addressed command records
   that no reservation on disk connects to;
2. standalone status verifies the shard manifest bytes against the digest
   the installed identity binds, never trusting a manifest because it
   parses; review passes the manifest it already verified;
3. a DONE shard record requires and verifies the raw response and its
   digest, the session, invocation, policy, result, claim, reservation,
   identity, input, and output attestations; removing and re-addressing
   linked records never preserves DONE; the output on disk must be the
   parsed raw response and carry the bound headers; sessions and prompts
   are unique across records;
4. the terminal command record is rederived from the reservation, claims,
   shard records, and outputs: overall result, per-shard states, record and
   output digests, calls, invocations, ceiling; zero or several terminal
   records for one command refuse;
5. an outputs-directory fsync failure after the link is installed removes
   the output from outputs/ and quarantines its bytes in the evidence root
   as REFUSED-output-*, which the next command refuses on.

No model call. `engine/reviewer.py` untouched.
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import uuid

PASS2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PASS2)
sys.path.insert(0, os.path.join(PASS2, "tools"))

from engine import canon  # noqa: E402
import run_reviewer_a  # noqa: E402
try:
    from tests.test_review_governance import (  # noqa: E402
        _ReviewHarness, GovernedShardSession, RaisingSession, RULING)
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_review_governance import (  # noqa: E402
        _ReviewHarness, GovernedShardSession, RaisingSession, RULING)

NEW_RULING = "18388418"
REVIEW_ATTEMPTS = run_reviewer_a.REVIEW_ATTEMPTS


def RECORD_SHA_OF(path):
    return canon.bytes_digest(canon.read_regular_bytes(path))


class _Root(_ReviewHarness):
    """The harness plus editors that re-address a record and keep the
    terminal record consistent with it, exactly as an adversary who owns
    the evidence root would."""

    def next_ruling(self):
        os.environ[run_reviewer_a.REVIEW_RULING_VAR] = NEW_RULING
        self.made.clear()

    def record_file(self, sid):
        d = self.path(run_reviewer_a.RUN_RECORDS_DIR)
        names = [n for n in os.listdir(d) if n.startswith(sid + ".")]
        self.assertEqual(len(names), 1, names)
        return os.path.join(d, names[0])

    def terminal_file(self):
        d = self.path(run_reviewer_a.COMMAND_RECORDS_DIR)
        names = sorted(os.listdir(d))
        self.assertEqual(len(names), 1, names)
        return os.path.join(d, names[0])

    def write_addressed(self, directory, prefix, obj):
        data = canon.canonical_bytes(obj)
        sha = canon.bytes_digest(data)
        with open(os.path.join(directory, f"{prefix}.{sha}.json"), "wb") as f:
            f.write(data)
        return sha

    def rewrite_terminal(self, mutate):
        """Rewrite T through `mutate(cmd)` and re-address it."""
        path = self.terminal_file()
        cmd = canon.load_json(path)
        mutate(cmd)
        os.unlink(path)
        return self.write_addressed(os.path.dirname(path),
                                    cmd["command_attempt_id"], cmd)

    def rewrite_record(self, sid, mutate, fix_terminal=True):
        """Rewrite the shard record through `mutate(rec)`, re-address it,
        and (by default) point the terminal record's listing at the new
        digest so the pair agrees with itself."""
        path = self.record_file(sid)
        rec = canon.load_json(path)
        mutate(rec)
        os.unlink(path)
        new_sha = self.write_addressed(os.path.dirname(path), sid, rec)
        if fix_terminal:
            def point(cmd):
                for s in cmd["shards"]:
                    if s["shard_id"] == sid:
                        s["record_sha256"] = new_sha
                        s["result"] = rec["result"]
                        s["output_sha256"] = rec.get("output_sha256")
                        s["phase"] = rec.get("phase")
                        s["error"] = rec.get("error")
                        s["cli_invocations"] = rec.get("cli_invocations")
                        s["model_calls"] = rec.get("model_calls")
            self.rewrite_terminal(point)
        return new_sha

    def rewrite_output(self, sid, obj):
        """Replace the installed output with `obj` and make the record and
        the terminal record attest the new bytes."""
        path = self.path(run_reviewer_a.OUTPUTS_DIR, f"{sid}.json")
        data = canon.canonical_bytes(obj)
        os.unlink(path)
        with open(path, "wb") as f:
            f.write(data)

        def attest(rec):
            rec["output_sha256"] = canon.bytes_digest(data)
            rec["output_byte_length"] = len(data)
        self.rewrite_record(sid, attest)

    def status_output(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            run_reviewer_a.status(self.out, self.a)
        return buf.getvalue()

    def assert_refused_before_reservation(self, needle, ids=None):
        err = str(self.review(ids=ids))
        self.assertIn(needle, err)
        self.assertEqual(self.made, [])
        return err


class ForeignArtifactsRefuseLoud(_Root):
    """Finding 1."""

    def test_unknown_root_entry_refuses(self):
        with open(self.path("notes.json"), "w") as f:
            f.write("{}")
        self.assert_refused_before_reservation("notes.json: not an artifact the harness writes")
        self.assertIsNone(self.reservation())

    def test_unknown_claim_artifact_refuses(self):
        os.makedirs(self.path(run_reviewer_a.CLAIMS_DIR))
        # a claim for a shard the bound manifest does not name
        canon.write_canonical(self.path(run_reviewer_a.CLAIMS_DIR, "shard-999.999.json"),
                              {"shard_id": "shard-999.999"})
        self.assert_refused_before_reservation("shard-999.999.json: not a shard the bound manifest names")
        os.unlink(self.path(run_reviewer_a.CLAIMS_DIR, "shard-999.999.json"))
        # a malformed claim for an unselected manifest shard: no command
        other = self.members[2]["shard_id"]
        with open(self.path(run_reviewer_a.CLAIMS_DIR, f"{other}.json"), "w") as f:
            f.write("not json")
        self.assert_refused_before_reservation(f"claims/{other}.json: unreadable")
        os.unlink(self.path(run_reviewer_a.CLAIMS_DIR, f"{other}.json"))
        # a well-formed claim naming a command no reservation on disk names
        canon.write_canonical(self.path(run_reviewer_a.CLAIMS_DIR, f"{other}.json"), {
            "shard_id": other, "command_attempt_id": str(uuid.uuid4()),
            "ruling_id": "18376200", "reservation_path":
                "reservations/review-ruling-18376200.json",
            "reservation_sha256": "0" * 64})
        self.assert_refused_before_reservation("no reservation on disk")
        self.assertIsNone(self.reservation())

    def test_claim_naming_another_shard_or_command_refuses(self):
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        other = self.members[2]["shard_id"]
        claim = self.claim(self.ids[0])
        # the real claim's content under another shard's name
        canon.write_canonical(self.path(run_reviewer_a.CLAIMS_DIR, f"{other}.json"), claim)
        self.next_ruling()
        self.assert_refused_before_reservation("content names", ids=[self.ids[1]])
        # a claim whose command is real but whose reservation digest is not
        # the reservation on disk
        canon.write_canonical(self.path(run_reviewer_a.CLAIMS_DIR, f"{other}.json"),
                              dict(claim, shard_id=other, reservation_sha256="0" * 64))
        self.assert_refused_before_reservation("reservation on disk", ids=[self.ids[1]])
        # a claim for a shard the reservation of its command does not name
        canon.write_canonical(self.path(run_reviewer_a.CLAIMS_DIR, f"{other}.json"),
                              dict(claim, shard_id=other))
        self.assert_refused_before_reservation("does not name", ids=[self.ids[1]])

    def test_claim_without_a_record_is_pinned_to_the_reservation_digest(self):
        # a claim the reservation names, for a shard with no record (NOT_RUN
        # after the first shard failed): only the store check can pin it
        self.queue.append(GovernedShardSession(response="{}"))
        self.assertEqual(self.review(), 1)
        self.assertIsNone(self.claim(self.ids[1]))
        claim = dict(self.claim(self.ids[0]), shard_id=self.ids[1],
                     input_sha256=self.members[1]["sha256"], reservation_sha256="0" * 64)
        canon.write_canonical(self.path(run_reviewer_a.CLAIMS_DIR, f"{self.ids[1]}.json"), claim)
        self.next_ruling()
        err = self.assert_refused_before_reservation(
            "its reservation digest is not the reservation on disk",
            ids=[self.members[2]["shard_id"]])
        self.assertNotIn("does not name its shard", err)

    def test_orphan_command_record_refuses(self):
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        cmd = canon.load_json(self.terminal_file())
        orphan = dict(cmd, command_attempt_id=str(uuid.uuid4()), ruling_id="18376200",
                      reservation_path="reservations/review-ruling-18376200.json")
        self.write_addressed(self.path(run_reviewer_a.COMMAND_RECORDS_DIR),
                             orphan["command_attempt_id"], orphan)
        self.next_ruling()
        self.assert_refused_before_reservation("no reservation on disk", ids=[self.ids[1]])
        # standalone status names it too, as a store problem
        self.assertIn("STORE PROBLEM: command-records/", self.status_output())
        self.assertIn("no reservation on disk", self.status_output())

    def test_artifacts_for_shards_the_manifest_does_not_name_refuse(self):
        unknown = "shard-999.999"
        for sub in (run_reviewer_a.OUTPUTS_DIR, run_reviewer_a.RUN_RECORDS_DIR,
                    run_reviewer_a.CLAIMS_DIR):
            os.makedirs(self.path(sub), exist_ok=True)
            if sub == run_reviewer_a.RUN_RECORDS_DIR:
                self.write_addressed(self.path(sub), unknown, {"shard_id": unknown})
            else:
                canon.write_canonical(self.path(sub, f"{unknown}.json"), {"shard_id": unknown})
            self.assert_refused_before_reservation("not a shard the bound manifest names")
            shutil.rmtree(self.path(sub))

    def test_unknown_reservation_name_refuses(self):
        os.makedirs(self.path(run_reviewer_a.RESERVATIONS_DIR), exist_ok=True)
        canon.write_canonical(self.path(run_reviewer_a.RESERVATIONS_DIR, "planted.json"), {})
        self.assert_refused_before_reservation("reservations/planted.json: not a reservation the harness writes")

    def test_a_governed_root_still_passes_the_store_check(self):
        # the real root's shapes: binding record, ledgers, transcripts,
        # preflight manifests and evidence, stale transcript and its
        # manifest, identity, run-record manifest, the binding reservation
        self.assertEqual(run_reviewer_a.review_store_problems(self.a), [])
        self.assertEqual(self.review(), 0, self.stdout)
        self.assertEqual(run_reviewer_a.review_store_problems(self.a), [])


class StatusTrustsOnlyTheBoundManifest(_Root):
    """Finding 2."""

    def _edit_manifest(self):
        path = os.path.join(self.out, "shard-manifest.json")
        manifest = canon.load_json(path)
        manifest["shards"].append(dict(self.members[0], shard_id="shard-999.1"))
        canon.write_canonical(path, manifest)

    def test_status_refuses_a_manifest_that_does_not_hash_to_the_bound_digest(self):
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        self._edit_manifest()
        with self.assertRaises(SystemExit) as ctx:
            self.states()
        self.assertIn("not the bound manifest", str(ctx.exception))
        with self.assertRaises(SystemExit) as ctx:
            self.status_output()
        self.assertIn("not the bound manifest", str(ctx.exception))
        # the command refuses in the same words, before anything
        self.next_ruling()
        self.assert_refused_before_reservation("not the bound manifest", ids=[self.ids[1]])

    def test_the_identitys_binding_outranks_the_bundles_declaration(self):
        # the manifest AND the bundle's declaration of its digest are
        # rewritten together, the identity untouched: the bundle now vouches
        # for the edited manifest, the identity does not, and status sides
        # with the identity
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        self._edit_manifest()
        bundle_path = os.path.join(self.out, "review-input-bundle.json")
        bundle = canon.load_json(bundle_path)
        bundle["shard_manifest"]["sha256"] = canon.file_sha256(
            os.path.join(self.out, "shard-manifest.json"))
        canon.write_canonical(bundle_path, bundle)
        with self.assertRaises(SystemExit) as ctx:
            self.states()
        self.assertIn("not the bound manifest", str(ctx.exception))

    def test_status_never_reads_the_manifest_through_a_link(self):
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        path = os.path.join(self.out, "shard-manifest.json")
        shutil.copy(path, os.path.join(self.root, "elsewhere.json"))
        os.unlink(path)
        os.symlink(os.path.join(self.root, "elsewhere.json"), path)
        with self.assertRaises(SystemExit) as ctx:
            self.states()
        self.assertIn("not a regular file", str(ctx.exception))

    def test_status_without_an_identity_still_hashes_the_manifest(self):
        os.unlink(self.path(run_reviewer_a.IDENTITY_FILE))
        self._edit_manifest()
        with self.assertRaises(SystemExit) as ctx:
            self.states()
        self.assertIn("not the bound manifest", str(ctx.exception))


class DoneNeedsEveryAttestation(_Root):
    """Finding 3."""

    def _done(self):
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        st = self.states()[self.ids[0]]
        self.assertEqual((st["state"], st["problems"]), ("DONE", []))

    def _assert_corrupt(self, needle):
        st = self.states()[self.ids[0]]
        self.assertEqual(st["state"], "CORRUPT", (needle, st))
        self.assertTrue(any(needle in p for p in st["problems"]), (needle, st["problems"]))
        # and the next command refuses before anything is reserved, whether
        # the store check or the shard recomputation names it first
        self.next_ruling()
        self.assert_refused_before_reservation("review refused", ids=[self.ids[1]])
        self.assertIsNone(self.reservation(NEW_RULING))

    def test_removing_and_readdressing_never_preserves_done(self):
        self._done()
        original = canon.load_json(self.record_file(self.ids[0]))
        for field, value, needle in (
                ("raw_response", None, "raw_response"),
                ("raw_response_sha256", None, "raw_response_sha256"),
                ("session_id", None, "session_id"),
                ("session_id", "", "session_id"),
                ("num_turns", None, "num_turns"),
                ("prompt_sha256", None, "prompt_sha256"),
                ("prompt_sha256", "not-a-digest", "prompt_sha256"),
                ("prompt_sha256", "a" * 64, "prompt_sha256 does not rederive"),
                ("claim_sha256", None, "claim_sha256"),
                ("claim_path", None, "claim_path"),
                ("claim_path", "claims/other.json", "claim_path"),
                ("output_path", None, "output_path"),
                ("output_byte_length", None, "output_byte_length"),
                ("output_sha256", None, "output_sha256"),
                ("started_utc", None, "started_utc"),
                ("phase", "install", "phase"),
                ("error", "edited", "error"),
                ("live_invocations_started", None, "live_invocations_started"),
                ("invocation_accounting", "unavailable", "invocation_accounting"),
                ("cli_invocation_log", [], "cli_invocation_log"),
                ("machine_corrections", None, "machine_corrections"),
                ("pre_call_record_verification", None, "pre_call_record_verification"),
                ("completeness_check", None, "completeness_check"),
                ("schema_report", None, "schema_report"),
                ("problems", ["completeness"], "problems"),
                ("observed_model_usage", None, "observed_model_usage"),
                ("input_path", None, "input path"),
                ("reservation_path", None, "reservation path"),
                ("auxiliary_model_violations", None, "auxiliary_model_violations"),
                ("attempts_allowed", None, "ruling's sentence"),
        ):
            def mutate(rec, field=field, value=value):
                rec.clear()
                rec.update(original)
                rec[field] = value
            self.rewrite_record(self.ids[0], mutate)
            self._assert_corrupt(needle)
        # a field removed outright, not nulled
        def drop(rec):
            rec.clear()
            rec.update(original)
            del rec["raw_response"]
        self.rewrite_record(self.ids[0], drop)
        self._assert_corrupt("raw_response")

    def test_raw_response_must_parse_to_the_installed_output(self):
        self._done()
        rec = canon.load_json(self.record_file(self.ids[0]))
        other = json.loads(rec["raw_response"])
        other["dispositions"][0]["rationale"] = "edited after the fact"
        text = json.dumps(other)

        def mutate(r):
            r["raw_response"] = text
            r["raw_response_sha256"] = canon.content_digest(text)
        self.rewrite_record(self.ids[0], mutate)
        self._assert_corrupt("raw response does not parse to the installed output")

    def test_output_must_carry_the_bound_headers_and_the_shard_id(self):
        self._done()
        out = canon.load_json(self.path(run_reviewer_a.OUTPUTS_DIR, f"{self.ids[0]}.json"))
        rec = canon.load_json(self.record_file(self.ids[0]))
        for field, value, needle in (
                ("reviewer_identity_sha256", "0" * 64, "bound headers"),
                ("shard_manifest_sha256", "0" * 64, "bound headers"),
                ("review_input_bundle_sha256", "0" * 64, "bound headers"),
                ("contract_sha256", "0" * 64, "bound headers"),
                ("shard_id", self.ids[1], "names shard")):
            edited = dict(out, **{field: value})
            text = json.dumps(edited)
            self.rewrite_output(self.ids[0], edited)

            def mutate(r, text=text):
                r["raw_response"] = text
                r["raw_response_sha256"] = canon.content_digest(text)
            self.rewrite_record(self.ids[0], mutate)
            self._assert_corrupt(needle)
            self.rewrite_output(self.ids[0], out)
            self.rewrite_record(self.ids[0], lambda r: r.update(
                raw_response=rec["raw_response"],
                raw_response_sha256=rec["raw_response_sha256"]))

    def test_session_and_prompt_are_unique_across_records(self):
        self.assertEqual(self.review(), 0, self.stdout)
        first = canon.load_json(self.record_file(self.ids[0]))
        self.rewrite_record(self.ids[1], lambda r: r.update(session_id=first["session_id"]))
        st = self.states()
        self.assertEqual(st[self.ids[1]]["state"], "CORRUPT", st[self.ids[1]])
        self.assertTrue(any("session_id" in p and "another record" in p
                            for p in st[self.ids[1]]["problems"]), st[self.ids[1]])
        self.rewrite_record(self.ids[1], lambda r: r.update(
            session_id="fake-session-9", prompt_sha256=first["prompt_sha256"]))
        st = self.states()
        self.assertEqual(st[self.ids[1]]["state"], "CORRUPT", st[self.ids[1]])
        self.assertTrue(any("prompt_sha256" in p and "another record" in p
                            for p in st[self.ids[1]]["problems"]), st[self.ids[1]])

    def test_a_failed_record_past_the_claim_cannot_drop_its_claim_digest(self):
        # the optional claim check was the hole; a FAIL record in phase
        # validation that nulls claim_sha256 (and is re-addressed with its
        # terminal record) is CORRUPT, not merely FAIL
        self.queue.append(GovernedShardSession(response="{}"))
        self.assertEqual(self.review(ids=[self.ids[0]]), 1)
        self.assertEqual(self.states()[self.ids[0]]["state"], "FAIL")
        self.rewrite_record(self.ids[0], lambda r: r.update(claim_sha256=None))
        st = self.states()[self.ids[0]]
        self.assertEqual(st["state"], "CORRUPT", st)
        self.assertTrue(any("lacks a valid claim_sha256" in p for p in st["problems"]), st)

    def test_claim_and_reservation_attestations_are_required_not_optional(self):
        self._done()
        # the claim's reservation digest is checked even when the record
        # drops its claim digest (the optional check was the hole)
        claim_path = self.path(run_reviewer_a.CLAIMS_DIR, f"{self.ids[0]}.json")
        claim = canon.load_json(claim_path)
        claim["reservation_sha256"] = "0" * 64
        os.unlink(claim_path)
        canon.write_canonical(claim_path, claim)
        self.rewrite_record(self.ids[0], lambda r: r.update(
            claim_sha256=canon.file_sha256(claim_path)))
        self._assert_corrupt("reservation digest is not the reservation on disk")


class TerminalRecordRederived(_Root):
    """Finding 4."""

    def _fail_then_not_run(self):
        self.queue.append(GovernedShardSession(response="{}"))
        self.assertEqual(self.review(), 1)
        cmd = canon.load_json(self.terminal_file())
        self.assertEqual([s["result"] for s in cmd["shards"]], ["FAIL", "NOT_RUN"])
        return cmd

    def _assert_command_problem(self, needle):
        cmds = run_reviewer_a.command_states(self.a)
        self.assertEqual(len(cmds), 1, cmds)
        self.assertTrue(any(needle in p for p in cmds[0]["problems"]), (needle, cmds[0]))
        # the next command refuses before anything is reserved, whichever
        # of the store check, the shard recomputation, or the command
        # recomputation names the rewrite first
        os.environ[run_reviewer_a.REVIEW_RULING_VAR] = NEW_RULING
        self.made.clear()
        err = str(self.review(ids=[self.members[2]["shard_id"]]))
        self.assertIn("review refused", err)
        self.assertEqual(self.made, [])
        self.assertIsNone(self.reservation(NEW_RULING))

    def test_duplicate_terminal_records_for_one_command_refuse(self):
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        cmd = canon.load_json(self.terminal_file())
        self.write_addressed(self.path(run_reviewer_a.COMMAND_RECORDS_DIR),
                             cmd["command_attempt_id"], dict(cmd, finished_utc="later"))
        self._assert_command_problem("more than one terminal command record")
        st = self.states()[self.ids[0]]
        self.assertEqual(st["state"], "CORRUPT", st)

    def test_not_run_shard_listed_as_done_is_rederived(self):
        self._fail_then_not_run()

        def forge(cmd):
            cmd["shards"][1].update(result="DONE", record_sha256="a" * 64,
                                    output_sha256="b" * 64, model_calls=1,
                                    cli_invocations=1, phase="finalized")
            cmd["model_calls"] = 2
            cmd["cli_invocations"] = 2
        self.rewrite_terminal(forge)
        self._assert_command_problem("no shard record on disk")

    def test_overall_result_is_rederived_from_the_shards(self):
        self._fail_then_not_run()
        self.rewrite_terminal(lambda cmd: cmd.update(result="PASS"))
        self._assert_command_problem("result PASS does not rederive")

    def test_counts_are_rederived_from_the_shard_records(self):
        self._fail_then_not_run()
        self.rewrite_terminal(lambda cmd: cmd.update(model_calls=0, cli_invocations=0))
        self._assert_command_problem("does not rederive")
        self.rewrite_terminal(lambda cmd: cmd.update(model_calls=1, cli_invocations=1))
        self.rewrite_terminal(lambda cmd: cmd["shards"][0].update(cli_invocations=5))
        # the shard side marks the shard CORRUPT on the same listing edit,
        # not only the command side
        st = self.states()[self.ids[0]]
        self.assertEqual(st["state"], "CORRUPT", st)
        self.assertIn("the terminal command record disagrees with the shard record",
                      st["problems"])
        self._assert_command_problem("disagrees with the shard record")

    def test_terminal_listing_must_match_the_reservation_order_and_inputs(self):
        self.assertEqual(self.review(), 0, self.stdout)
        self.rewrite_terminal(lambda cmd: cmd["shards"].reverse())
        self._assert_command_problem("does not list the reservation's shards")
        self.rewrite_terminal(lambda cmd: cmd["shards"].reverse())
        self.rewrite_terminal(lambda cmd: cmd["shards"][0].update(input_sha256="0" * 64))
        self._assert_command_problem("input digest")

    def test_not_run_with_a_record_on_disk_is_rederived(self):
        self.assertEqual(self.review(), 0, self.stdout)
        self.rewrite_terminal(lambda cmd: (cmd["shards"][1].update(
            result="NOT_RUN", record_sha256=None, output_sha256=None,
            model_calls=0, cli_invocations=None, phase=None),
            cmd.update(result="FAIL", model_calls=1, cli_invocations=1)))
        self._assert_command_problem("shard record on disk")
        st = self.states()[self.ids[1]]
        self.assertEqual(st["state"], "CORRUPT", st)

    def test_reservation_path_and_ceiling_are_rederived(self):
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        self.rewrite_terminal(lambda cmd: cmd.update(
            reservation_path="reservations/review-ruling-18376200.json"))
        self._assert_command_problem("reservation path")
        self.rewrite_terminal(lambda cmd: cmd.update(
            reservation_path=f"reservations/review-ruling-{RULING}.json", call_ceiling=2))
        self._assert_command_problem("call_ceiling")


class LegitimateRootsAreAccepted(_Root):
    """The stricter recomputation must accept every root the harness's
    own exits produce: a false CORRUPT or refusal on a legitimate root is
    a defect of the same rank as a missed forgery."""

    def _accepted(self, label):
        cmds = run_reviewer_a.command_states(self.a)
        self.assertTrue(all(c["problems"] == [] for c in cmds), (label, cmds))
        states = self.states()
        self.assertNotIn("CORRUPT", {s["state"] for s in states.values()},
                         (label, {k: v for k, v in states.items() if v["problems"]}))
        problems = run_reviewer_a.review_store_problems(
            self.a, run_reviewer_a.bound_manifest(self.out, self.a))
        self.assertEqual(problems, [], label)
        out = self.status_output()
        self.assertNotIn("PROBLEM", out, (label, out))

    def test_validation_and_policy_failures(self):
        self.queue.append(GovernedShardSession(response="{}"))
        self.assertEqual(self.review(), 1)
        self._accepted("validation failure then NOT_RUN")

    def test_session_refused_before_the_claim(self):
        s = GovernedShardSession()
        s.timeout = 5
        self.queue.append(s)
        self.assertEqual(self.review(), 1)
        self._accepted("session refused, ruling spent, every shard NOT_RUN")

    def test_record_store_down_leaves_unattested_with_an_output(self):
        real = run_reviewer_a.write_review_record

        def writer(directory, prefix, record):
            if directory.endswith(run_reviewer_a.RUN_RECORDS_DIR):
                raise OSError("record store down")
            return real(directory, prefix, record)
        run_reviewer_a.write_review_record = writer
        self.review_raises(OSError)
        run_reviewer_a.write_review_record = real
        self.assertEqual(self.command_record()["shards"][0]["result"], "UNATTESTED")
        self.assertIsNotNone(self.output_bytes(self.ids[0]))
        self._accepted("UNATTESTED with an installed output")

    def test_interrupted_claim_write(self):
        real = self.saved_os_write

        def os_write(fd, view):
            if b'"foundry-pass-2-shard-claim/' in bytes(view)[:120]:
                raise KeyboardInterrupt()
            return real(fd, view)
        canon.os_write = os_write
        self.review_raises(KeyboardInterrupt)
        canon.os_write = real
        self._accepted("claim interrupted, record in phase claim")

    def test_manifest_failure_after_a_shard(self):
        def broken(a_out=None):
            raise OSError("index disk full")
        real = run_reviewer_a.write_run_record_manifest
        run_reviewer_a.write_run_record_manifest = broken
        self.assertEqual(self.review(), 1)
        run_reviewer_a.write_run_record_manifest = real
        self._accepted("DONE then manifest failure, FAIL command")

    def test_two_commands_and_a_lost_claim_race(self):
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        self.next_ruling()
        self.assertEqual(self.review(ids=[self.ids[1]]), 0, self.stdout)
        self._accepted("two commands, two terminal records")

    def test_interrupt_inside_the_reservation_write(self):
        real = self.saved_os_write

        def os_write(fd, view):
            if b'"foundry-pass-2-review-reservation/' in bytes(view)[:120]:
                raise KeyboardInterrupt()
            return real(fd, view)
        canon.os_write = os_write
        self.review_raises(KeyboardInterrupt)
        canon.os_write = real
        self._accepted("reservation interrupted, terminal record in phase reservation")


class PassOneClosures(_Root):
    """The isolated adversary's findings on the first close of this head
    (Foundry-Evidence/18388418-review-path/pass1/REPORT.md), each
    reproduced with its mechanics and now refused."""

    def _done(self):
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        st = self.states()[self.ids[0]]
        self.assertEqual((st["state"], st["problems"]), ("DONE", []))
        return self.ids[0]

    def _doctor(self, sid):
        """The adversary's A1: an output with none of the bound headers, the
        record re-addressed with a prompt digest no prompt renders to."""
        forged = dict(canon.load_json(self.path(run_reviewer_a.OUTPUTS_DIR, f"{sid}.json")),
                      reviewer_identity_sha256="0" * 64, contract_sha256="0" * 64,
                      review_input_bundle_sha256="0" * 64, shard_manifest_sha256="0" * 64)
        text = json.dumps(forged)
        self.rewrite_output(sid, forged)
        self.rewrite_record(sid, lambda r: r.update(
            raw_response=text, raw_response_sha256=canon.content_digest(text),
            prompt_sha256="a" * 64))

    def test_finding_1_deleting_the_identity_never_restores_done(self):
        sid = self._done()
        self._doctor(sid)
        self.assertEqual(self.states()[sid]["state"], "CORRUPT")
        os.unlink(self.path(run_reviewer_a.IDENTITY_FILE))
        store = run_reviewer_a.review_store_problems(
            self.a, run_reviewer_a.bound_manifest(self.out, self.a))
        self.assertTrue(any("absent or not a regular file while review artifacts exist"
                            in p for p in store), store)
        st = self.states()[sid]
        self.assertEqual(st["state"], "CORRUPT", st)
        self.assertTrue(any("no identity on disk" in p for p in st["problems"]), st)
        self.assertIn("STORE PROBLEM: reviewer-identity.json", self.status_output())

    def test_finding_1_a_linked_identity_refuses_in_words(self):
        sid = self._done()
        self._doctor(sid)
        ident = self.path(run_reviewer_a.IDENTITY_FILE)
        shutil.copy(ident, os.path.join(self.root, "identity-elsewhere.json"))
        os.unlink(ident)
        os.symlink(os.path.join(self.root, "identity-elsewhere.json"), ident)
        for call in (self.states, self.status_output):
            with self.assertRaises(SystemExit) as ctx:
                call()
            self.assertIn("not a regular file", str(ctx.exception))
        problems = run_reviewer_a.review_store_problems(self.a, None)
        self.assertTrue(any("absent or not a regular file" in p for p in problems), problems)
        self.next_ruling()
        self.assert_refused_before_reservation("not a regular file", ids=[self.ids[1]])

    def test_finding_4_a_malformed_identity_binding_never_falls_back_to_the_bundle(self):
        self._done()
        path = self.path(run_reviewer_a.IDENTITY_FILE)
        original = canon.load_json(path)
        for value in (None, "not-a-digest", ""):
            identity = json.loads(json.dumps(original))
            if value is None:
                del identity["bindings"]["SHARD_MANIFEST_SHA256"]
            else:
                identity["bindings"]["SHARD_MANIFEST_SHA256"] = value
            os.unlink(path)
            canon.write_canonical(path, identity)
            with self.assertRaises(SystemExit) as ctx:
                run_reviewer_a.bound_manifest(self.out, self.a)
            self.assertIn("no well-formed shard manifest binding", str(ctx.exception))
            with self.assertRaises(SystemExit):
                self.status_output()
        os.unlink(path)
        with open(path, "wb") as f:
            f.write(b"not json")
        with self.assertRaises(SystemExit) as ctx:
            self.states()
        self.assertIn("malformed", str(ctx.exception))

    def _replace_output(self, sid, forged):
        text = json.dumps(forged)
        self.rewrite_output(sid, forged)
        self.rewrite_record(sid, lambda r: r.update(
            raw_response=text, raw_response_sha256=canon.content_digest(text)))
        name = os.path.basename(self.record_file(sid))
        self.rewrite_terminal(lambda cmd: [s.update(
            record_path=f"{run_reviewer_a.RUN_RECORDS_DIR}/{name}")
            for s in cmd["shards"] if s["shard_id"] == sid])

    def _assert_corrupt(self, sid, needle):
        st = self.states()[sid]
        self.assertEqual(st["state"], "CORRUPT", (needle, st))
        self.assertTrue(any(needle in p for p in st["problems"]), (needle, st["problems"]))

    def test_finding_2_the_outputs_substance_is_recomputed(self):
        sid = self._done()
        original = canon.load_json(self.path(run_reviewer_a.OUTPUTS_DIR, f"{sid}.json"))
        # D2: no dispositions at all, the completeness block rewritten to match
        forged = json.loads(json.dumps(original))
        forged["dispositions"] = []
        forged["completeness"] = {"input_artifact_count": 0, "output_disposition_count": 0,
                                  "duplicate_artifact_ids": [], "missing_artifact_ids": [],
                                  "unexpected_artifact_ids": []}
        self._replace_output(sid, forged)
        self._assert_corrupt(sid, "completeness")
        self.next_ruling()
        self.assert_refused_before_reservation("review refused", ids=[self.ids[1]])
        # one disposition's digests no longer the shard's
        forged = json.loads(json.dumps(original))
        forged["dispositions"][0]["record_sha256"] = "0" * 64
        self._replace_output(sid, forged)
        self._assert_corrupt(sid, "digest-not-preserved")
        # a schema-invalid verdict
        forged = json.loads(json.dumps(original))
        forged["dispositions"][0]["verdict"] = "maybe"
        self._replace_output(sid, forged)
        self._assert_corrupt(sid, "schema")
        # the record's own completeness check edited to disagree
        self._replace_output(sid, original)
        self.assertEqual(self.states()[sid]["state"], "DONE")
        self.rewrite_record(sid, lambda r: r["completeness_check"].update(
            output_disposition_count=99))
        self._assert_corrupt(sid, "completeness_check")
        # the record's schema report not a pass
        self.rewrite_record(sid, lambda r: r.update(
            completeness_check=canon.load_json(self.record_file(sid))["completeness_check"]))
        self.rewrite_record(sid, lambda r: (r["completeness_check"].update(
            output_disposition_count=len(original["dispositions"])),
            r["schema_report"].update(returncode=1)))
        self._assert_corrupt(sid, "schema_report")

    def test_finding_5_an_interrupt_during_the_post_link_fsync_quarantines(self):
        outputs = self.path(run_reviewer_a.OUTPUTS_DIR)
        sid = self.ids[0]
        real_fsync = os.fsync

        def fsync(fd):
            st = os.fstat(fd)
            if os.path.isdir(outputs) and (st.st_dev, st.st_ino) == (
                    os.stat(outputs).st_dev, os.stat(outputs).st_ino) and \
                    os.path.lexists(os.path.join(outputs, f"{sid}.json")):
                raise KeyboardInterrupt("signal during fsync")
            return real_fsync(fd)
        os.fsync = fsync
        try:
            self.review_raises(KeyboardInterrupt, ids=[sid])
        finally:
            os.fsync = real_fsync
        self.assertEqual([n for n in os.listdir(outputs) if not n.startswith(".")], [])
        self.assertEqual(len([n for n in os.listdir(self.a)
                              if n.startswith("REFUSED-output-")]), 1)
        rec = self.record(sid)
        self.assertEqual((rec["result"], rec["phase"]), ("FAIL", "install"))
        self.assertEqual(self.states()[sid]["state"], "FAIL")

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root reads anything")
    def test_finding_6_an_unreadable_reservation_refuses_in_words(self):
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        res = self.path(run_reviewer_a.RESERVATIONS_DIR,
                        f"{run_reviewer_a.REVIEW_RESERVATION_PREFIX}{RULING}.json")
        os.chmod(res, 0o000)
        try:
            problems = run_reviewer_a.review_store_problems(
                self.a, run_reviewer_a.bound_manifest(self.out, self.a))
            self.assertTrue(any("unreadable" in p for p in problems), problems)
            self.next_ruling()
            self.assert_refused_before_reservation("review refused", ids=[self.ids[1]])
            self.assertIn("STORE PROBLEM", self.status_output())
        finally:
            os.chmod(res, 0o644)


class PassTwoClosures(_Root):
    """The second isolated pass's findings on the pass-one closes
    (Foundry-Evidence/18388418-review-path/pass2/REPORT.md), each
    reproduced with its mechanics and now refused."""

    def _unattested_no_output(self):
        """The adversary's B1: the call raises and the record store is down,
        so the harness writes UNATTESTED with no output at all."""
        real = self.saved["write_review_record"]

        def writer(directory, prefix, record):
            if directory.endswith(run_reviewer_a.RUN_RECORDS_DIR):
                raise OSError("record store down")
            return real(directory, prefix, record)
        run_reviewer_a.write_review_record = writer
        self.queue.append(RaisingSession(RuntimeError("cli died")))
        self.review_raises(OSError, ids=[self.ids[0]])
        run_reviewer_a.write_review_record = real
        entry = self.command_record()["shards"][0]
        self.assertEqual((entry["result"], entry["output_sha256"]), ("UNATTESTED", None))
        self.assertIsNone(self.output_bytes(self.ids[0]))

    def test_finding_1_a_planted_output_on_an_unattested_shard_is_named(self):
        sid = self.ids[0]
        self._unattested_no_output()
        self.assertEqual(self.states()[sid]["state"], "UNATTESTED")
        with open(self.path(run_reviewer_a.OUTPUTS_DIR, f"{sid}.json"), "wb") as f:
            f.write(canon.canonical_bytes({"planted": True}))
        st = self.states()[sid]
        self.assertEqual(st["state"], "CORRUPT", st)
        self.assertTrue(any("output present for an unattested shard" in p
                            for p in st["problems"]), st)
        cmds = run_reviewer_a.command_states(self.a)
        self.assertTrue(any("with no output but one is on disk" in p
                            for p in cmds[0]["problems"]), cmds)
        self.next_ruling()
        self.assert_refused_before_reservation("review refused", ids=[self.ids[1]])
        self.assertIn("PROBLEMS", self.status_output())

    def test_finding_1_nulling_the_unattested_entry_cannot_swap_the_output(self):
        # the adversary's B2: E7 with an installed output, the entry's
        # digests nulled, the bytes replaced
        real = self.saved["write_review_record"]

        def writer(directory, prefix, record):
            if directory.endswith(run_reviewer_a.RUN_RECORDS_DIR):
                raise OSError("record store down")
            return real(directory, prefix, record)
        run_reviewer_a.write_review_record = writer
        self.review_raises(OSError, ids=[self.ids[0]])
        run_reviewer_a.write_review_record = real
        sid = self.ids[0]
        self.assertEqual(self.states()[sid]["state"], "UNATTESTED")
        self.rewrite_terminal(lambda cmd: cmd["shards"][0].update(
            output_sha256=None, output_path=None))
        with open(self.path(run_reviewer_a.OUTPUTS_DIR, f"{sid}.json"), "wb") as f:
            f.write(canon.canonical_bytes({"forged": True}))
        st = self.states()[sid]
        self.assertEqual(st["state"], "CORRUPT", st)
        cmds = run_reviewer_a.command_states(self.a)
        self.assertTrue(any("no output but one is on disk" in p for p in cmds[0]["problems"]),
                        cmds)
        # and the genuine entry with a swapped output is caught too
        self.rewrite_terminal(lambda cmd: cmd["shards"][0].update(
            output_sha256="a" * 64, output_path=f"outputs/{sid}.json"))
        cmds = run_reviewer_a.command_states(self.a)
        self.assertTrue(any("not on disk as attested" in p for p in cmds[0]["problems"]), cmds)

    def _done(self):
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        st = self.states()[self.ids[0]]
        self.assertEqual((st["state"], st["problems"]), ("DONE", []))
        return self.ids[0]

    def test_finding_2_a_missing_toolchain_is_named_as_such_never_as_forgery(self):
        sid = self._done()
        # a verdict already computed in this process is reused (same output
        # bytes, same ratified validator); the toolchain is consulted only
        # when a verdict is not yet known, so it is cleared here
        saved_path = os.environ.get("PATH", "")
        empty = os.path.join(self.root, "empty-bin")
        os.makedirs(empty)
        os.environ["PATH"] = empty
        run_reviewer_a._REVALIDATION_CACHE.clear()
        try:
            st = self.states()[sid]
        finally:
            os.environ["PATH"] = saved_path
        self.assertEqual(st["state"], "CORRUPT", st)
        self.assertTrue(any("schema could not be revalidated" in p and "toolchain" in p
                            for p in st["problems"]), st)
        self.assertFalse(any("does not validate" in p for p in st["problems"]), st)
        # ajv missing: the validator starts and dies without a verdict
        saved_root = run_reviewer_a.REPO_ROOT
        run_reviewer_a.REPO_ROOT = os.path.join(self.root, "no-node-modules")
        os.makedirs(run_reviewer_a.REPO_ROOT)
        run_reviewer_a._REVALIDATION_CACHE.clear()
        try:
            st = self.states()[sid]
        finally:
            run_reviewer_a.REPO_ROOT = saved_root
        self.assertTrue(any("schema could not be revalidated" in p and "without a verdict" in p
                            for p in st["problems"]), st)
        self.assertFalse(any("does not validate" in p for p in st["problems"]), st)
        # the toolchain back: the evidence was good throughout
        self.assertEqual(self.states()[sid]["state"], "DONE")

    def test_finding_3_the_validator_is_held_to_the_ratified_contract(self):
        sid = self._done()
        validator = os.path.join(run_reviewer_a.ARI, "validate-reviewer-output-v0.1.mjs")
        with open(validator, "rb") as f:
            ratified = f.read()
        try:
            with open(validator, "wb") as f:
                f.write(b"process.exit(0);\n")
            st = self.states()[sid]
            self.assertEqual(st["state"], "CORRUPT", st)
            self.assertTrue(any("is not the one the ratified contract binds" in p
                                for p in st["problems"]), st)
        finally:
            with open(validator, "wb") as f:
                f.write(ratified)
        self.assertEqual(canon.file_sha256(validator),
                         run_reviewer_a.ratified_validator_sha(self.out))
        self.assertEqual(self.states()[sid]["state"], "DONE")

    def test_an_incomplete_output_is_refused_even_when_both_copies_agree_with_it(self):
        # the direct check on the recomputation, not only the two copy
        # checks: dispositions emptied, then the record's completeness_check
        # AND the output's own block rewritten to the (bad) recomputed dict
        sid = self._done()
        member = [m for m in self.members if m["shard_id"] == sid][0]
        out = canon.load_json(self.path(run_reviewer_a.OUTPUTS_DIR, f"{sid}.json"))
        bad = {"input_artifact_count": len(member["artifact_ids"]),
               "output_disposition_count": 0, "duplicate_artifact_ids": [],
               "missing_artifact_ids": sorted(member["artifact_ids"]),
               "unexpected_artifact_ids": []}
        forged = dict(out, dispositions=[], completeness=bad)
        text = json.dumps(forged)
        self.rewrite_output(sid, forged)
        self.rewrite_record(sid, lambda r: r.update(
            raw_response=text, raw_response_sha256=canon.content_digest(text),
            completeness_check=bad))
        st = self.states()[sid]
        self.assertEqual(st["state"], "CORRUPT", st)
        self.assertTrue(any("once each (completeness)" in p for p in st["problems"]), st)
        self.assertFalse(any("completeness_check is not" in p or "own completeness block" in p
                             for p in st["problems"]), st)

    def test_finding_4_the_outputs_own_completeness_block_is_recomputed(self):
        sid = self._done()
        out = canon.load_json(self.path(run_reviewer_a.OUTPUTS_DIR, f"{sid}.json"))
        forged = json.loads(json.dumps(out))
        forged["completeness"]["input_artifact_count"] = 0
        forged["completeness"]["output_disposition_count"] = 0
        text = json.dumps(forged)
        self.rewrite_output(sid, forged)
        self.rewrite_record(sid, lambda r: r.update(
            raw_response=text, raw_response_sha256=canon.content_digest(text)))
        st = self.states()[sid]
        self.assertEqual(st["state"], "CORRUPT", st)
        self.assertTrue(any("own completeness block" in p for p in st["problems"]), st)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root reads anything")
    def test_finding_5_unreadable_objects_refuse_in_words_from_review_and_status(self):
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        cases = (
            (self.path(run_reviewer_a.IDENTITY_FILE), "unreadable"),
            (os.path.join(self.out, "shard-manifest.json"), "unreadable"),
            (os.path.join(self.out, "review-input-bundle.json"), "could not be read"),
            (self.path(run_reviewer_a.OUTPUTS_DIR), "not listable"),
        )
        for target, needle in cases:
            os.chmod(target, 0o000)
            try:
                self.next_ruling()
                err = str(self.review(ids=[self.ids[1]]))
                self.assertIn(needle, err, (target, err))
                self.assertEqual(self.made, [])
                with self.assertRaises(SystemExit) as ctx:
                    self.status_output()
                self.assertIn(needle, str(ctx.exception), (target, str(ctx.exception)))
            finally:
                os.chmod(target, 0o755 if os.path.isdir(target) else 0o644)
        # command_states shares the identity reader
        os.chmod(self.path(run_reviewer_a.IDENTITY_FILE), 0o000)
        try:
            with self.assertRaises(SystemExit) as ctx:
                run_reviewer_a.command_states(self.a)
            self.assertIn("unreadable", str(ctx.exception))
        finally:
            os.chmod(self.path(run_reviewer_a.IDENTITY_FILE), 0o644)

    def test_finding_6_a_failed_quarantine_is_said_in_words(self):
        real_link = self.saved["os_link"]
        target = self.path(run_reviewer_a.OUTPUTS_DIR, f"{self.ids[0]}.json")

        def os_link(src, dst):
            real_link(src, dst)
            if dst == target:
                with open(dst, "r+b") as f:
                    f.seek(-2, os.SEEK_END)
                    f.write(b"X\n")
        run_reviewer_a.os_link = os_link
        real_rename = os.rename

        def rename(src, dst):
            if os.path.basename(dst).startswith("REFUSED-output-"):
                raise OSError(1, "Operation not permitted")
            return real_rename(src, dst)
        os.rename = rename
        buf = io.StringIO()
        try:
            with contextlib.redirect_stderr(buf):
                self.assertEqual(self.review(ids=[self.ids[0]]), 1)
        finally:
            os.rename = real_rename
        self.assertIn("QUARANTINE FAILED", buf.getvalue())
        rec = self.record(self.ids[0])
        self.assertIn("nothing was moved", rec["error"])
        self.assertEqual(self.states()[self.ids[0]]["state"], "CORRUPT")

    def test_note_7_status_names_a_moved_bundle_as_the_cause(self):
        self._done()
        bundle_path = os.path.join(self.out, "review-input-bundle.json")
        bundle = canon.load_json(bundle_path)
        bundle["planted"] = True
        canon.write_canonical(bundle_path, bundle)
        with self.assertRaises(SystemExit) as ctx:
            self.status_output()
        self.assertIn("bundle changed since identity was bound", str(ctx.exception))


class _Shapes(_Root):
    """Roots in the shapes the third and fourth isolated passes attacked:
    an UNATTESTED shard that DID install an output (the harness's own E7
    exit, record store down), editors that replace that output and
    re-attest it in the terminal record, and a DONE shard."""

    def _unattested_with_output(self):
        real = self.saved["write_review_record"]

        def writer(directory, prefix, record):
            if directory.endswith(run_reviewer_a.RUN_RECORDS_DIR):
                raise OSError("record store down")
            return real(directory, prefix, record)
        run_reviewer_a.write_review_record = writer
        self.review_raises(OSError, ids=[self.ids[0]])
        run_reviewer_a.write_review_record = real
        sid = self.ids[0]
        st = self.states()[sid]
        self.assertEqual((st["state"], st["problems"]), ("UNATTESTED", []))
        return sid

    def _replace_unattested(self, sid, data):
        path = self.path(run_reviewer_a.OUTPUTS_DIR, f"{sid}.json")
        os.unlink(path)
        with open(path, "wb") as f:
            f.write(data)
        digest = canon.bytes_digest(data)
        self.rewrite_terminal(lambda cmd: [s.update(output_sha256=digest)
                                           for s in cmd["shards"] if s["shard_id"] == sid])
        st = self.states()[sid]
        self.assertEqual(st["state"], "CORRUPT", st)
        return st["problems"]

    def _replace_unattested_ok(self, sid, data):
        path = self.path(run_reviewer_a.OUTPUTS_DIR, f"{sid}.json")
        os.unlink(path)
        with open(path, "wb") as f:
            f.write(data)
        digest = canon.bytes_digest(data)
        self.rewrite_terminal(lambda cmd: [s.update(output_sha256=digest)
                                           for s in cmd["shards"] if s["shard_id"] == sid])
        st = self.states()[sid]
        self.assertEqual((st["state"], st["problems"]), ("UNATTESTED", []))

    def _done(self):
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        st = self.states()[self.ids[0]]
        self.assertEqual((st["state"], st["problems"]), ("DONE", []))
        return self.ids[0]


class PassThreeClosures(_Shapes):
    """The third isolated pass's findings on the pass-two closes
    (Foundry-Evidence/18388418-review-path/pass3/REPORT.md), each
    reproduced with its mechanics and now refused."""

    def test_finding_1_an_unattested_output_is_held_like_a_done_one(self):
        sid = self._unattested_with_output()
        genuine = canon.load_json(self.path(run_reviewer_a.OUTPUTS_DIR, f"{sid}.json"))
        # A2: bytes that are not an output at all, the terminal record re-addressed
        problems = self._replace_unattested(
            sid, b'{"shard_id":"shard-000.0","not":"an output"}\n')
        self.assertTrue(any("unattested output" in p and "names shard" in p
                            for p in problems), problems)
        # the headers zeroed, everything else genuine
        forged = dict(genuine, reviewer_identity_sha256="0" * 64)
        problems = self._replace_unattested(sid, canon.canonical_bytes(forged))
        self.assertTrue(any("bound headers" in p for p in problems), problems)
        # the dispositions emptied
        forged = dict(genuine, dispositions=[])
        problems = self._replace_unattested(sid, canon.canonical_bytes(forged))
        self.assertTrue(any("completeness" in p for p in problems), problems)
        # the genuine bytes back: legitimate again
        self._replace_unattested_ok(sid, canon.canonical_bytes(genuine))

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root reads anything")
    def test_finding_2_unreadable_ratified_files_refuse_in_words(self):
        for name in ("isolated-reviewer-contract-v0.3.json",
                     "reviewer-task-template-v0.1.md",
                     "reviewer-output-v0.1.schema.json",
                     "reviewer-system-prompt-v0.1.md"):
            path = os.path.join(run_reviewer_a.ARI, name)
            os.chmod(path, 0o000)
            try:
                err = str(self.review(ids=[self.ids[0]]))
            finally:
                os.chmod(path, 0o644)
            self.assertIn("could not be read", err, (name, err))
            self.assertEqual(self.made, [])

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root reads anything")
    def test_finding_3_the_path_gate_runs_before_any_read(self):
        res_dir = self.path(run_reviewer_a.RESERVATIONS_DIR)
        os.chmod(res_dir, 0o000)
        try:
            err = str(self.review(ids=[self.ids[0]]))
        finally:
            os.chmod(res_dir, 0o755)
        self.assertIn("not listable", err)
        self.assertIn("evidence path boundary", err)
        self.assertEqual(self.made, [])

    def test_finding_4_unparseable_bytes_are_a_fact_about_the_evidence(self):
        sid = self._done()
        out = canon.load_json(self.path(run_reviewer_a.OUTPUTS_DIR, f"{sid}.json"))
        forged = dict(out, planted_by_adversary_key=float("nan"))
        text = json.dumps(forged)
        self.rewrite_output(sid, forged)
        self.rewrite_record(sid, lambda r: r.update(
            raw_response=text, raw_response_sha256=canon.content_digest(text)))
        st = self.states()[sid]
        self.assertEqual(st["state"], "CORRUPT", st)
        self.assertTrue(any("not JSON the ratified validator can parse" in p
                            for p in st["problems"]), st)
        self.assertFalse(any("toolchain" in p for p in st["problems"]), st)
        self.assertFalse(any("planted_by_adversary_key" in p for p in st["problems"]), st)

    def test_finding_5_the_cache_key_names_every_input_to_the_verdict(self):
        self._done()
        keys = list(run_reviewer_a._REVALIDATION_CACHE)
        self.assertTrue(keys)
        self.assertTrue(all(len(k) == 3 and all(isinstance(x, str) and len(x) == 64
                                                for x in k) for k in keys), keys)

    def test_finding_6_the_live_validator_needs_an_object_and_the_pass_marker(self):
        ok, _report = run_reviewer_a.schema_validator([])
        self.assertFalse(ok)
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        out = canon.load_json(self.path(run_reviewer_a.OUTPUTS_DIR, f"{self.ids[0]}.json"))
        ok, _report = run_reviewer_a.schema_validator(out)
        self.assertTrue(ok)

    def test_finding_7_completeness_is_byte_equal(self):
        sid = self._done()
        out = canon.load_json(self.path(run_reviewer_a.OUTPUTS_DIR, f"{sid}.json"))
        forged = json.loads(json.dumps(out))
        forged["completeness"]["input_artifact_count"] = float(
            forged["completeness"]["input_artifact_count"])
        text = json.dumps(forged)
        self.rewrite_output(sid, forged)
        self.rewrite_record(sid, lambda r: r.update(
            raw_response=text, raw_response_sha256=canon.content_digest(text)))
        st = self.states()[sid]
        self.assertEqual(st["state"], "CORRUPT", st)
        self.assertTrue(any("own completeness block" in p for p in st["problems"]), st)

    def test_finding_8_what_the_bundle_names_is_held_to_its_binding(self):
        self._done()
        bundle = canon.load_json(os.path.join(self.out, "review-input-bundle.json"))
        rel = bundle["bindings"]["control_records_bundle"]["location"]
        path = os.path.join(run_reviewer_a.PASS2, rel)
        with open(path, "rb") as f:
            original = f.read()
        try:
            with open(path, "ab") as f:
                f.write(b"\n")
            with self.assertRaises(SystemExit) as ctx:
                self.status_output()
            self.assertIn("bound artifact control_records_bundle", str(ctx.exception))
            self.next_ruling()
            self.assert_refused_before_reservation("bound artifact control_records_bundle",
                                                   ids=[self.ids[1]])
        finally:
            with open(path, "wb") as f:
                f.write(original)
        self.assertEqual(run_reviewer_a.bound_artifact_problems(self.out), [])


ALWAYS_PASS_VALIDATOR = """#!/usr/bin/env node
import process from "node:process";
const args = process.argv.slice(2);
for (const p of args.slice(1)) console.log(`${p}: PASS`);
process.exit(0);
"""


class PassFourClosures(_Shapes):
    """The fourth isolated pass's findings on the pass-three closes
    (Foundry-Evidence/18388418-review-path/pass4/REPORT.md), each
    reproduced with its mechanics and now refused. Finding 6 (canon's
    is_regular raising on an unlistable directory for direct shard_states
    callers) is stated as outside this authorization, not closed."""

    NOT_CANONICAL = "the installed bytes are not the canonical form the harness writes"

    def test_finding_1_an_unattested_output_must_be_the_harness_bytes(self):
        sid = self._unattested_with_output()
        genuine = canon.load_json(self.path(run_reviewer_a.OUTPUTS_DIR, f"{sid}.json"))
        # P1: the same values in a serialization the harness never writes
        forged = json.dumps(genuine, indent=2, sort_keys=False).encode("utf-8")
        self.assertNotEqual(forged, canon.canonical_bytes(genuine))
        problems = self._replace_unattested(sid, forged)
        self.assertIn("unattested output: " + self.NOT_CANONICAL, problems)
        # P2: a lone surrogate, bytes the install path can never produce
        surrogate = json.loads(json.dumps(genuine))
        surrogate["dispositions"][0]["rationale"] = "\ud800"
        with self.assertRaises(UnicodeEncodeError):
            canon.canonical_bytes(surrogate)
        forged = (json.dumps(surrogate, ensure_ascii=True, sort_keys=True,
                             separators=(",", ":")) + "\n").encode("ascii")
        problems = self._replace_unattested(sid, forged)
        self.assertTrue(any("not JSON the harness can write" in p for p in problems),
                        problems)
        # P3: two dispositions members in one object; every reader takes the last
        text = canon.canonical_bytes(genuine).decode("utf-8").rstrip("\n")
        rejected = json.loads(text)
        for d in rejected["dispositions"]:
            d.update(verdict="reject", reason_codes=["other-material-error"],
                     rationale="the second copy", proposed_correction=None)
        second = json.dumps(rejected["dispositions"], sort_keys=True,
                            separators=(",", ":"))
        forged = (text[:-1] + ',"dispositions":' + second + "}\n").encode("utf-8")
        self.assertEqual(json.loads(forged)["dispositions"][0]["verdict"], "reject")
        problems = self._replace_unattested(sid, forged)
        self.assertIn("unattested output: " + self.NOT_CANONICAL, problems)
        # the genuine bytes back: legitimate again
        self._replace_unattested_ok(sid, canon.canonical_bytes(genuine))

    def test_finding_1_the_done_path_holds_the_same_bytes(self):
        sid = self._done()
        path = self.path(run_reviewer_a.OUTPUTS_DIR, f"{sid}.json")
        out = canon.load_json(path)
        forged = json.dumps(out, indent=2, sort_keys=False).encode("utf-8")
        os.unlink(path)
        with open(path, "wb") as f:
            f.write(forged)
        text = forged.decode("utf-8")
        self.rewrite_record(sid, lambda r: r.update(
            output_sha256=canon.bytes_digest(forged), output_byte_length=len(forged),
            raw_response=text, raw_response_sha256=canon.content_digest(text)))
        st = self.states()[sid]
        self.assertEqual(st["state"], "CORRUPT", st)
        self.assertIn(self.NOT_CANONICAL, st["problems"])

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root reads anything")
    def test_finding_2_unreadable_command_inputs_refuse_in_words(self):
        identity = canon.load_json(self.path("reviewer-identity.json"))
        records = [n for n in os.listdir(self.a)
                   if n.startswith(run_reviewer_a.BINDING_RECORD_PREFIX)]
        self.assertEqual(len(records), 1, records)
        cases = [
            ("next shard input", os.path.join(self.out, self.members[0]["path"]),
             "input could not be read"),
            ("binding attempt record", self.path(records[0]),
             "binding attempt record"),
            ("PASSED transcript",
             self.path(os.path.basename(identity["leak_probe_evidence_path"])),
             "the probe evidence the identity names could not be read"),
            ("binding reservation",
             self.path(run_reviewer_a.RESERVATIONS_DIR,
                       os.path.basename(identity["reservation_path"])),
             "the head reservation the identity names could not be read"),
        ]
        for label, path, needle in cases:
            self.assertTrue(os.path.isfile(path), (label, path))
            os.chmod(path, 0o000)
            try:
                err = str(self.review(ids=[self.ids[0]]))
            finally:
                os.chmod(path, 0o644)
            self.assertIn(needle, err, (label, err))
            self.assertIn("could not be read", err, (label, err))
            self.assertEqual(self.made, [], label)

    def test_finding_3_bound_artifacts_resolve_from_the_repo_root(self):
        rel = "experiments/foundry-pass-2/tests/pin4-bound-artifact.json"
        target = os.path.join(run_reviewer_a.REPO_ROOT, rel)
        data = canon.canonical_bytes({"probe": "pin4 bound artifact"})
        bundle_path = os.path.join(self.out, "review-input-bundle.json")
        bundle = canon.load_json(bundle_path)

        def bind(binding):
            edited = json.loads(json.dumps(bundle))
            edited["bindings"]["pin4"] = binding
            canon.write_canonical(bundle_path, edited)
            return run_reviewer_a.bound_artifact_problems(self.out)
        try:
            with open(target, "wb") as f:
                f.write(data)
            # the emitter's convention, repo-root relative: verified
            self.assertEqual(bind({"path": rel, "sha256": canon.bytes_digest(data)}), [])
            problems = bind({"path": rel, "sha256": "0" * 64})
            self.assertEqual(len(problems), 1, problems)
            self.assertIn(f"bound artifact pin4 ({rel}) hashes to", problems[0])
        finally:
            os.unlink(target)
        # an absent bound file is named, never skipped
        self.assertEqual(bind({"path": rel, "sha256": "0" * 64}),
                         [f"bound artifact pin4 ({rel}) is absent"])
        # a location that escapes or is absolute is refused
        for bad in ("../" + rel, "/" + rel):
            problems = bind({"location": bad, "sha256": "0" * 64})
            self.assertEqual(len(problems), 1, problems)
            self.assertIn("names a location outside the repository", problems[0])
        # a sentence where the location goes binds no file and is skipped
        self.assertEqual(bind({"location": "private until both reviewer outputs "
                                           "are fixed", "sha256": "0" * 64}), [])
        # and the command refuses on the absent bound artifact before any session
        bind({"path": rel, "sha256": "0" * 64})
        self._rebind_after_bundle_edit()
        self.assert_refused_before_reservation(f"bound artifact pin4 ({rel}) is absent",
                                               ids=[self.ids[0]])

    def test_finding_4_the_live_path_refuses_an_unratified_validator(self):
        ratified = run_reviewer_a.ratified_validator_sha(self.out)
        tmp = tempfile.mkdtemp(prefix="pin4-ari-")
        ari = os.path.join(tmp, "ari")
        shutil.copytree(run_reviewer_a.ARI, ari)
        with open(os.path.join(ari, "validate-reviewer-output-v0.1.mjs"), "w",
                  encoding="utf-8") as f:
            f.write(ALWAYS_PASS_VALIDATOR)
        saved = {k: getattr(run_reviewer_a, k)
                 for k in ("ARI", "OUTPUT_SCHEMA", "_RATIFIED_VALIDATOR_SHA")}
        run_reviewer_a.ARI = ari
        run_reviewer_a.OUTPUT_SCHEMA = os.path.join(ari, "reviewer-output-v0.1.schema.json")
        try:
            # once a command has named the ratified validator, a substitute
            # that prints the marker is not a pass
            run_reviewer_a._RATIFIED_VALIDATOR_SHA = ratified
            ok, report = run_reviewer_a.schema_validator(
                {"shard_id": "shard-000.0", "not": "an output"})
            self.assertFalse(ok)
            self.assertNotEqual(report["validator_sha256"], ratified)
            self.assertIsNone(report["returncode"])
            self.assertIn("not the one the ratified contract binds", report["stderr_head"])
            # through the command: the shard's own validation fails and the
            # substitute's verdict is never installed
            self.assertEqual(self.review(ids=[self.ids[0]]), 1, self.stdout)
            rec = self.record(self.ids[0])
            self.assertEqual((rec["result"], rec["phase"]), ("FAIL", "validation"),
                             rec.get("error"))
            self.assertIn("schema", rec["error"])
            self.assertIsNone(self.output_bytes(self.ids[0]))
            self.assertEqual(len(self.made), 1)
        finally:
            for k, v in saved.items():
                setattr(run_reviewer_a, k, v)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_finding_5_a_swapped_schema_is_a_did_not_run(self):
        sid = self._done()
        out_bytes = self.output_bytes(sid)
        sha = run_reviewer_a.ratified_validator_sha(self.out)
        schema_sha = canon.file_sha256(run_reviewer_a.OUTPUT_SCHEMA)
        self.assertEqual(run_reviewer_a.revalidate_output(None, out_bytes, sha, schema_sha),
                         "pass")
        tmp = tempfile.mkdtemp(prefix="pin4-schema-")
        other = os.path.join(tmp, "reviewer-output-v0.1.schema.json")
        canon.write_canonical(other, {
            "$schema": "https://json-schema.org/draft/2020-12/schema", "type": "string"})
        saved_schema = run_reviewer_a.OUTPUT_SCHEMA
        saved_cache = dict(run_reviewer_a._REVALIDATION_CACHE)
        run_reviewer_a.OUTPUT_SCHEMA = other
        try:
            verdict = run_reviewer_a.revalidate_output(None, out_bytes, sha, schema_sha)
            self.assertTrue(verdict.startswith("did-not-run: the output schema on disk"),
                            verdict)
            # the digest is what does it: without one the swapped schema is run
            self.assertEqual(run_reviewer_a.revalidate_output(None, out_bytes, sha),
                             "reject")
            # a schema file that will not parse is the machine's fault, digest
            # or no digest: never "the installed bytes are not JSON"
            with open(other, "wb") as f:
                f.write(b"{not json")
            for args in ((sha,), (sha, schema_sha)):
                verdict = run_reviewer_a.revalidate_output(None, out_bytes, *args)
                self.assertTrue(verdict.startswith("did-not-run: the output schema on disk"),
                                verdict)
                self.assertNotIn("installed bytes", verdict)
        finally:
            run_reviewer_a.OUTPUT_SCHEMA = saved_schema
            run_reviewer_a._REVALIDATION_CACHE.clear()
            run_reviewer_a._REVALIDATION_CACHE.update(saved_cache)
            shutil.rmtree(tmp, ignore_errors=True)


class AriFindingsOn7caff55(_Root):
    """Ari's three blocking findings on 7caff55 (room 40; authorization
    18391672), each reproduced with Ari's mechanics and now refused, with
    the legitimate root beside each as the control."""

    def store(self):
        return run_reviewer_a.review_store_problems(
            self.a, run_reviewer_a.bound_manifest(self.out, self.a))

    def root_problems(self):
        return run_reviewer_a._root_artifact_problems(self.a)

    def test_A_a_shaped_transcript_must_hash_to_its_name_and_be_named(self):
        self.assertEqual(self.root_problems(), [])
        # Ari's probe: the right shape over the bytes "{}"
        name = "leak-probe-transcript-PASSED-" + "0" * 64 + ".json"
        with open(self.path(name), "wb") as f:
            f.write(b"{}\n")
        self.assertEqual(self.root_problems(), [f"{name}: does not hash to its name"])
        self.assert_refused_before_reservation(f"{name}: does not hash to its name",
                                               ids=[self.ids[0]])
        os.unlink(self.path(name))
        # a transcript that hashes to its name and that nothing names
        data = canon.canonical_bytes({"forged": "transcript"})
        name = f"leak-probe-transcript-FAILED-{canon.bytes_digest(data)}.json"
        with open(self.path(name), "wb") as f:
            f.write(data)
        self.assertEqual(self.root_problems(),
                         [f"{name}: no identity, trusted binding attempt record, or "
                          "preflight manifest member names it"])
        self.assert_refused_before_reservation("names it", ids=[self.ids[0]])
        os.unlink(self.path(name))
        # the genuine PASSED transcript, rewritten under its own name
        identity = canon.load_json(self.path("reviewer-identity.json"))
        genuine = self.path(identity["leak_probe_evidence_path"])
        original = canon.read_regular_bytes(genuine)
        os.unlink(genuine)
        with open(genuine, "wb") as f:
            f.write(original + b"\n")
        self.assertIn(f"{os.path.basename(genuine)}: does not hash to its name",
                      self.root_problems())
        os.unlink(genuine)
        with open(genuine, "wb") as f:
            f.write(original)
        # the legitimate root, before and after a governed command
        self.assertEqual(self.root_problems(), [])
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        self.assertEqual(self.store(), [])

    def _ledger(self):
        return canon.load_json(self.path(run_reviewer_a.BINDING_LEDGER))

    def _write_ledger(self, ledger):
        path = self.path(run_reviewer_a.BINDING_LEDGER)
        os.unlink(path)
        canon.write_canonical(path, ledger)

    def _write_record(self, rec):
        data = canon.canonical_bytes(rec)
        name = f"{run_reviewer_a.BINDING_RECORD_PREFIX}{canon.bytes_digest(data)}.json"
        with open(self.path(name), "wb") as f:
            f.write(data)
        return name, canon.bytes_digest(data)

    def _forged_transcript(self, label="FAILED"):
        data = canon.canonical_bytes({"forged": "transcript", "label": label})
        name = f"leak-probe-transcript-{label}-{canon.bytes_digest(data)}.json"
        with open(self.path(name), "wb") as f:
            f.write(data)
        return name, canon.bytes_digest(data)

    def test_A_a_binding_record_must_hash_to_its_name_and_be_ledgered_to_vouch(self):
        records = [n for n in os.listdir(self.a)
                   if n.startswith(run_reviewer_a.BINDING_RECORD_PREFIX)]
        self.assertEqual(len(records), 1, records)
        rec_path = self.path(records[0])
        original = canon.read_regular_bytes(rec_path)
        os.unlink(rec_path)
        with open(rec_path, "wb") as f:
            f.write(original + b"\n")
        problems = self.root_problems()
        self.assertIn(f"{records[0]}: does not hash to its name", problems)
        # the ledger names a record that is no longer on disk
        self.assertTrue(any("names record" in p and "not on disk" in p for p in problems),
                        problems)
        self.assertIn(f"STORE PROBLEM: {records[0]}: does not hash to its name",
                      self.status_output())
        os.unlink(rec_path)
        with open(rec_path, "wb") as f:
            f.write(original)
        self.assertEqual(self.root_problems(), [])
        # the fifth pass's finding 1: a second record, hashing to its name and
        # naming a planted transcript and a stray reservation, vouches for
        # nothing because no ledger line names it
        tname, tsha = self._forged_transcript()
        stray = os.path.join(self.path(run_reviewer_a.RESERVATIONS_DIR), "c" * 40 + ".json")
        with open(stray, "wb") as f:
            f.write(b"{}\n")
        rec = dict(canon.load_json(rec_path), attempt_id=str(uuid.uuid4()), result="FAIL",
                   evidence_path=tname, evidence_sha256=tsha,
                   reservation_path=f"{run_reviewer_a.RESERVATIONS_DIR}/{'c' * 40}.json",
                   reservation_sha256=canon.bytes_digest(b"{}\n"))
        rname, rsha = self._write_record(rec)
        problems = self.root_problems()
        self.assertIn(f"{rname}: not in the binding ledger; it vouches for nothing", problems)
        self.assertTrue(any(p.startswith(tname) and "names it" in p for p in problems), problems)
        self.assertTrue(any("names this head reservation" in p for p in problems), problems)
        self.assert_refused_before_reservation("vouches for nothing", ids=[self.ids[0]])
        # ledgered, the same record vouches for both: the stated limit, a
        # prior attempt forged whole
        ledger = self._ledger()
        line = dict(ledger["attempts"][0], attempt_id=rec["attempt_id"], result="FAIL",
                    head=rec["head"], evidence_path=tname, evidence_sha256=tsha,
                    reservation_path=rec["reservation_path"], record_sha256=rsha,
                    identity_sha256=None)
        self._write_ledger(dict(ledger, attempts=ledger["attempts"] + [line]))
        self.assertEqual(self.root_problems(), [])
        # a ledger line that disagrees with the record on any bound field
        # withdraws the vouch
        bad = dict(line, evidence_sha256="f" * 64)
        self._write_ledger(dict(ledger, attempts=ledger["attempts"] + [bad]))
        problems = self.root_problems()
        self.assertIn(f"{rname}: disagrees with its binding ledger line; it vouches for "
                      "nothing", problems)
        os.unlink(self.path(rname))
        os.unlink(self.path(tname))
        os.unlink(stray)
        self._write_ledger(ledger)
        self.assertEqual(self.root_problems(), [])

    def test_A_a_record_under_the_wrong_name_vouches_for_nothing_even_when_ledgered(self):
        """Mutant N72 of the final matrix: with the refusal's `continue`
        removed, a record under the wrong name was still refused but its
        bytes entered the on-disk set and, with a ledger line naming those
        bytes, it vouched for a transcript. The refusal must also withdraw
        the vouch: the transcript stays unnamed and the ledger line names a
        record that is not on disk."""
        rec_path = self.path([n for n in os.listdir(self.a)
                              if n.startswith(run_reviewer_a.BINDING_RECORD_PREFIX)][0])
        tname, tsha = self._forged_transcript()
        rec = dict(canon.load_json(rec_path), attempt_id=str(uuid.uuid4()), result="FAIL",
                   evidence_path=tname, evidence_sha256=tsha, identity_sha256=None)
        rname, rsha = self._write_record(rec)
        wrong = f"{run_reviewer_a.BINDING_RECORD_PREFIX}{'d' * 64}.json"
        os.rename(self.path(rname), self.path(wrong))
        ledger = self._ledger()
        line = dict(ledger["attempts"][0], attempt_id=rec["attempt_id"], result="FAIL",
                    head=rec["head"], evidence_path=tname, evidence_sha256=tsha,
                    reservation_path=rec["reservation_path"], record_sha256=rsha,
                    identity_sha256=None)
        self._write_ledger(dict(ledger, attempts=ledger["attempts"] + [line]))
        problems = self.root_problems()
        self.assertIn(f"{wrong}: does not hash to its name", problems)
        self.assertTrue(any(p.startswith(tname) and "names it" in p for p in problems), problems)
        self.assertTrue(any(f"names record {rsha[:12]}" in p and "not on disk" in p
                            for p in problems), problems)
        self.assert_refused_before_reservation("does not hash to its name", ids=[self.ids[0]])
        os.unlink(self.path(wrong))
        os.unlink(self.path(tname))
        self._write_ledger(ledger)
        self.assertEqual(self.root_problems(), [])

    def test_A_the_identitys_own_record_vouches_without_a_ledger_line(self):
        """The harness writes the record before the ledger line; a kill in
        between leaves a root every byte of which is the harness's (sixth
        isolated pass, finding 1)."""
        ledger = self._ledger()
        self.assertEqual(len(ledger["attempts"]), 1)
        self._write_ledger(dict(ledger, attempts=[]))
        self.assertEqual(self.root_problems(), [])
        os.unlink(self.path(run_reviewer_a.BINDING_LEDGER))
        self.assertEqual(self.root_problems(), [])
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        # but a prior attempt's record with no line still vouches for nothing
        tname, tsha = self._forged_transcript()
        rec_path = self.path([n for n in os.listdir(self.a)
                              if n.startswith(run_reviewer_a.BINDING_RECORD_PREFIX)][0])
        rec = dict(canon.load_json(rec_path), attempt_id=str(uuid.uuid4()), result="FAIL",
                   head="a" * 40, evidence_path=tname, evidence_sha256=tsha)
        rname, _sha = self._write_record(rec)
        problems = self.root_problems()
        self.assertIn(f"{rname}: not in the binding ledger; it vouches for nothing", problems)
        self.assertTrue(any(p.startswith(tname) for p in problems), problems)

    def test_A_a_copy_of_the_identitys_own_record_is_named_by_the_store_check(self):
        """Seventh isolated pass, finding 1: a copy of the identity's own
        record, repointed at foreign artifacts under a new content-addressed
        name, satisfied the own rule; review() refused it as a second record
        naming the attempt, but the store check said nothing."""
        rec_path = self.path([n for n in os.listdir(self.a)
                              if n.startswith(run_reviewer_a.BINDING_RECORD_PREFIX)][0])
        tname, tsha = self._forged_transcript("PASSED")
        rec = dict(canon.load_json(rec_path), evidence_path=tname, evidence_sha256=tsha)
        self._write_record(rec)
        problems = self.root_problems()
        self.assertIn("2 binding attempt records claim the identity's own attempt; exactly "
                      "one is the identity's", problems)
        # review() refuses one layer earlier, from the identity's own chain
        self.assert_refused_before_reservation("exactly one is required", ids=[self.ids[0]])

    def test_A_a_preflight_manifest_vouches_only_for_its_own_kind(self):
        tname, tsha = self._forged_transcript("PASSED")
        manifest_path = self.path(run_reviewer_a.reviewer.FAILED_PREFLIGHT_MANIFEST)
        canon.write_canonical(manifest_path, {"artifact_version": "x", "members": [
            {"attempt_id": "x", "path": tname, "sha256": tsha}]})
        self.assertTrue(any(p.startswith(tname) and "names it" in p
                            for p in self.root_problems()), self.root_problems())
        os.unlink(manifest_path)
        manifest_path = self.path(run_reviewer_a.reviewer.PASSED_PREFLIGHT_MANIFEST)
        passed = canon.load_json(manifest_path)
        os.unlink(manifest_path)
        canon.write_canonical(manifest_path, dict(passed, members=passed["members"] + [
            {"attempt_id": "x", "path": tname, "sha256": tsha}]))
        self.assertEqual(self.root_problems(), [])

    def test_A_a_second_pass_record_at_the_bound_head_is_refused(self):
        rec_path = self.path([n for n in os.listdir(self.a)
                              if n.startswith(run_reviewer_a.BINDING_RECORD_PREFIX)][0])
        identity = canon.load_json(self.path("reviewer-identity.json"))
        rec = dict(canon.load_json(rec_path), attempt_id=str(uuid.uuid4()),
                   identity_sha256="e" * 64)
        rname, rsha = self._write_record(rec)
        ledger = self._ledger()
        line = dict(ledger["attempts"][0], attempt_id=rec["attempt_id"], record_sha256=rsha,
                    identity_sha256="e" * 64)
        self._write_ledger(dict(ledger, attempts=ledger["attempts"] + [line]))
        self.assertEqual(rec["head"], identity["head"])
        problems = self.root_problems()
        self.assertIn(f"{rname}: a PASS record at the bound head that is not the identity's "
                      "own attempt", problems)
        self.assert_refused_before_reservation("not the identity's own attempt",
                                               ids=[self.ids[0]])

    def test_A_a_preflight_manifest_member_vouches_only_with_the_bytes_digest(self):
        tname, tsha = self._forged_transcript("FAILED")
        manifest_path = self.path(run_reviewer_a.reviewer.FAILED_PREFLIGHT_MANIFEST)
        self.assertFalse(os.path.lexists(manifest_path))
        canon.write_canonical(manifest_path, {"artifact_version": "x", "members": [
            {"attempt_id": "legacy", "path": tname, "sha256": "0" * 64}]})
        self.assertEqual(self.root_problems(),
                         [f"{tname}: does not hash to what its referrer attests"])
        os.unlink(manifest_path)
        canon.write_canonical(manifest_path, {"artifact_version": "x", "members": [
            {"attempt_id": "legacy", "path": tname, "sha256": tsha}]})
        self.assertEqual(self.root_problems(), [])
        # a member path with directory components attests nothing
        os.unlink(manifest_path)
        canon.write_canonical(manifest_path, {"artifact_version": "x", "members": [
            {"attempt_id": "legacy", "path": "../" + tname, "sha256": tsha}]})
        self.assertTrue(any(p.startswith(tname) and "names it" in p
                            for p in self.root_problems()), self.root_problems())

    @unittest.skipUnless(os.path.isdir(os.path.join(run_reviewer_a.OUT, "reviewer-a")),
                         "the real evidence root is not on this machine")
    def test_A_the_real_evidence_root_is_accepted_read_only(self):
        """The real root holds a FAILED transcript from before records were
        ledgered, named only by the failed-preflight and stale manifests;
        the close must accept it. Read-only: nothing under the real root
        is opened for writing."""
        real = os.path.join(run_reviewer_a.OUT, "reviewer-a")
        before = sorted((n, os.lstat(os.path.join(real, n)).st_mtime_ns)
                        for n in os.listdir(real))
        self.assertEqual(run_reviewer_a._root_artifact_problems(real), [])
        after = sorted((n, os.lstat(os.path.join(real, n)).st_mtime_ns)
                       for n in os.listdir(real))
        self.assertEqual(before, after)

    def test_A_referrers_are_kept_by_kind_and_a_null_digest_attests_nothing(self):
        rec_path = self.path([n for n in os.listdir(self.a)
                              if n.startswith(run_reviewer_a.BINDING_RECORD_PREFIX)][0])
        ledger = self._ledger()
        res_dir = self.path(run_reviewer_a.RESERVATIONS_DIR)
        # a ledgered record whose evidence fields name a head reservation
        # vouches for no reservation, and whose reservation digest is null
        # attests nothing
        with open(os.path.join(res_dir, "d" * 40 + ".json"), "wb") as f:
            f.write(b'{"anything": "not a reservation"}\n')
        rec = dict(canon.load_json(rec_path), attempt_id=str(uuid.uuid4()), result="FAIL",
                   evidence_path=f"{run_reviewer_a.RESERVATIONS_DIR}/{'d' * 40}.json",
                   evidence_sha256=canon.file_sha256(os.path.join(res_dir, "d" * 40 + ".json")),
                   reservation_path=f"{run_reviewer_a.RESERVATIONS_DIR}/{'d' * 40}.json",
                   reservation_sha256=None)
        rname, rsha = self._write_record(rec)
        line = dict(ledger["attempts"][0], attempt_id=rec["attempt_id"], result="FAIL",
                    head=rec["head"], evidence_path=rec["evidence_path"],
                    evidence_sha256=rec["evidence_sha256"],
                    reservation_path=rec["reservation_path"], record_sha256=rsha,
                    identity_sha256=None)
        self._write_ledger(dict(ledger, attempts=ledger["attempts"] + [line]))
        problems = self.root_problems()
        self.assertEqual(problems, [f"{run_reviewer_a.RESERVATIONS_DIR}/{'d' * 40}.json: a "
                                    "referrer attests no digest for it"])

    def test_A_a_stale_transcript_must_be_in_the_manifest(self):
        data = canon.canonical_bytes({"stale": "transcript"})
        name = f"leak-probe-transcript-STALE-{canon.bytes_digest(data)}.json"
        with open(self.path(name), "wb") as f:
            f.write(data)
        self.assertEqual(self.root_problems(),
                         [f"{name}: not a member of {run_reviewer_a.STALE_MANIFEST}"])
        manifest = self.path(run_reviewer_a.STALE_MANIFEST)
        # a member with another digest, or a path with directory components,
        # attests nothing (fifth isolated pass, finding 2)
        canon.write_canonical(manifest, {
            "artifact_version": "foundry-pass-2-stale-transcript-manifest/experimental-v0.1",
            "members": [{"stale_path": name, "sha256": "0" * 64}]})
        self.assertEqual(self.root_problems(),
                         [f"{name}: does not hash to what {run_reviewer_a.STALE_MANIFEST} "
                          "attests"])
        os.unlink(manifest)
        canon.write_canonical(manifest, {
            "artifact_version": "foundry-pass-2-stale-transcript-manifest/experimental-v0.1",
            "members": [{"stale_path": "../../" + name, "sha256": canon.bytes_digest(data)}]})
        self.assertEqual(self.root_problems(),
                         [f"{name}: not a member of {run_reviewer_a.STALE_MANIFEST}"])
        os.unlink(manifest)
        canon.write_canonical(manifest, {
            "artifact_version": "foundry-pass-2-stale-transcript-manifest/experimental-v0.1",
            "members": [{"stale_path": name, "sha256": canon.bytes_digest(data)}]})
        self.assertEqual(self.root_problems(), [])
        os.unlink(self.path(name))
        with open(self.path(name), "wb") as f:
            f.write(data + b"\n")
        self.assertEqual(self.root_problems(), [f"{name}: does not hash to its name"])

    def test_B_a_head_reservation_must_be_named_and_hash_to_its_referrer(self):
        res_dir = self.path(run_reviewer_a.RESERVATIONS_DIR)
        # Ari's probe: a stray head reservation over the bytes "{}"
        stray = os.path.join(res_dir, "c" * 40 + ".json")
        with open(stray, "wb") as f:
            f.write(b"{}\n")
        self.assertEqual(self.root_problems(), [
            f"{run_reviewer_a.RESERVATIONS_DIR}/{'c' * 40}.json: no identity or trusted "
            "binding attempt record names this head reservation"])
        self.assert_refused_before_reservation("names this head reservation",
                                               ids=[self.ids[0]])
        os.unlink(stray)
        # the identity's own reservation, edited in place
        identity = canon.load_json(self.path("reviewer-identity.json"))
        genuine = self.path(identity["reservation_path"])
        original = canon.read_regular_bytes(genuine)
        os.unlink(genuine)
        with open(genuine, "wb") as f:
            f.write(original + b"\n")
        self.assertEqual(self.root_problems(), [
            f"{identity['reservation_path']}: does not hash to what its referrer attests"])
        os.unlink(genuine)
        with open(genuine, "wb") as f:
            f.write(original)
        self.assertEqual(self.root_problems(), [])
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        self.assertEqual(self.store(), [])

    def test_C_not_run_counts_are_zero_and_totals_under_the_ceiling(self):
        # Ari's mechanics: shard one fails validation, shard two is NOT_RUN
        self.queue.append(GovernedShardSession(response="not json"))
        self.assertEqual(self.review(), 1)
        cmd = self.command_record()
        self.assertEqual([s["result"] for s in cmd["shards"]], ["FAIL", "NOT_RUN"])
        self.assertEqual([c["problems"] for c in run_reviewer_a.command_states(self.a)],
                         [[]])

        def inflate(c):
            c["shards"][1]["model_calls"] = 999
            c["shards"][1]["cli_invocations"] = 999
            c["model_calls"] += 999
            c["cli_invocations"] += 999
        self.rewrite_terminal(inflate)
        problems = run_reviewer_a.command_states(self.a)[0]["problems"]
        self.assertIn(f"terminal record lists {self.ids[1]} as NOT_RUN with calls or "
                      "invocations", problems)
        self.assertTrue(any(p.startswith("terminal record model_calls 1000 exceed the "
                                         "call ceiling 2") for p in problems), problems)
        self.assertTrue(any(p.startswith("terminal record cli_invocations 1000 exceed "
                                         "the call ceiling 2") for p in problems), problems)
        self.next_ruling()
        self.assert_refused_before_reservation("not finalized or not consistent",
                                               ids=[self.ids[1]])

    def test_C_a_fail_entry_may_carry_one_call_and_no_more(self):
        self.queue.append(GovernedShardSession(response="not json"))
        self.assertEqual(self.review(), 1)
        self.assertEqual([c["problems"] for c in run_reviewer_a.command_states(self.a)],
                         [[]])
        # the fifth pass's finding 4: one FAIL entry absorbing the whole
        # ceiling, the record restated to match, the totals under the ceiling
        self.rewrite_record(self.ids[0], lambda r: r.update(model_calls=2, cli_invocations=2))
        self.rewrite_terminal(lambda c: c.update(model_calls=2, cli_invocations=2))
        problems = run_reviewer_a.command_states(self.a)[0]["problems"]
        self.assertIn(f"terminal record lists {self.ids[0]} as FAIL with more than the one "
                      "call a shard may make", problems)

    def test_C_an_unattested_entry_may_carry_one_call_and_no_more(self):
        real = self.saved["write_review_record"]

        def writer(directory, prefix, record):
            if directory.endswith(run_reviewer_a.RUN_RECORDS_DIR):
                raise OSError("record store down")
            return real(directory, prefix, record)
        run_reviewer_a.write_review_record = writer
        self.review_raises(OSError, ids=[self.ids[0]])
        run_reviewer_a.write_review_record = real
        cmd = self.command_record()
        entry = cmd["shards"][0]
        self.assertEqual(entry["result"], "UNATTESTED")
        self.assertIn(entry["model_calls"], (0, 1))
        self.assertEqual([c["problems"] for c in run_reviewer_a.command_states(self.a)],
                         [[]])
        self.rewrite_terminal(lambda c: c["shards"][0].update(model_calls=2)
                              or c.update(model_calls=c["model_calls"] + 1))
        problems = run_reviewer_a.command_states(self.a)[0]["problems"]
        self.assertIn(f"terminal record lists {self.ids[0]} as UNATTESTED with more "
                      "than the one call a shard may make", problems)


class StrictIntegerAtEverySite(_Root):
    """Gate card v1.0, section 3.2 (authorization 18404868; Ari, review of
    3c84363): every count, ceiling, or attempt limit read from evidence is
    an exact JSON integer. A boolean or a non-integer number compares
    equal to an integer in Python (`True == 1`, `1.0 == 1`), so each site
    that once compared by value is pinned here with a lookalike: the site
    refuses in its own words, and the next governed command refuses before
    any session. The identity, its binding record, and the observed usage
    are pinned in tests/test_identity_binding.py (ReviewTimeEnforcement)."""

    LOOKALIKES = (True, 1.0)

    def test_the_helper_rejects_every_lookalike(self):
        for bad in (True, False, 1.0, 0.0, 1e0, -0.0, "1", None, [1], {"n": 1}):
            with self.subTest(value=bad):
                self.assertFalse(run_reviewer_a._exact_int(bad))
                self.assertFalse(run_reviewer_a._exact_int(bad, 0, 1))
        for good in (0, 1, 2, -1):
            self.assertTrue(run_reviewer_a._exact_int(good))
        self.assertTrue(run_reviewer_a._exact_int(1, 1))
        self.assertTrue(run_reviewer_a._exact_int(1, 0, 1))
        self.assertFalse(run_reviewer_a._exact_int(2, 0, 1))
        self.assertTrue(run_reviewer_a._exact_int_or_none(None, 0))
        self.assertTrue(run_reviewer_a._exact_int_or_none(0, 0))
        self.assertFalse(run_reviewer_a._exact_int_or_none(False, 0))
        self.assertFalse(run_reviewer_a._exact_int_or_none(0.0, 0))

    def _next_refuses(self, needle):
        self.next_ruling()
        self.assert_refused_before_reservation(needle, ids=[self.members[2]["shard_id"]])
        os.environ[run_reviewer_a.REVIEW_RULING_VAR] = RULING

    def test_site_reservation_ceiling_and_attempts(self):
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        path = self.path(run_reviewer_a.RESERVATIONS_DIR,
                         f"{run_reviewer_a.REVIEW_RESERVATION_PREFIX}{RULING}.json")
        original = canon.read_regular_bytes(path)
        needle = "reservation ceiling or attempts are not the exact integers"
        for field, bad in (("call_ceiling", 1.0), ("call_ceiling", True),
                           ("attempts_allowed", 1.0), ("attempts_allowed", True)):
            with self.subTest(field=field, value=bad):
                res = canon.load_json(path)
                res[field] = bad
                os.unlink(path)
                canon.write_canonical(path, res)
                # the reservation is judged where it is used: by every record
                # and every command record that names it
                st = self.states()[self.ids[0]]
                self.assertEqual(st["state"], "CORRUPT", st)
                self.assertTrue(any(needle in p for p in st["problems"]), st)
                cmds = run_reviewer_a.command_states(self.a)
                self.assertTrue(any(needle in p for p in cmds[0]["problems"]), cmds)
                # the claim's digest pin names the rewritten reservation first;
                # the next command refuses before any session either way
                self._next_refuses("review refused")
                os.unlink(path)
                with open(path, "wb") as f:
                    f.write(original)
        self.next_ruling()
        self.assertEqual(self.review(ids=[self.members[2]["shard_id"]]), 0, self.stdout)

    def test_site_done_record_counts(self):
        sid = self.ids[0]
        self.assertEqual(self.review(ids=[sid]), 0, self.stdout)
        for field in ("live_invocations_started", "cli_invocations", "model_calls",
                      "attempts_allowed"):
            for bad in self.LOOKALIKES:
                with self.subTest(field=field, value=bad):
                    good = canon.load_json(self.record_file(sid))[field]
                    self.rewrite_record(sid, lambda rec: rec.update({field: bad}))
                    st = self.states()[sid]
                    self.assertEqual(st["state"], "CORRUPT", st)
                    self.assertIn(f"a DONE record lacks a valid {field}", st["problems"])
                    if field != "live_invocations_started":
                        # the ruling's sentence on the accounting names it too
                        self.assertIn("accounting, verdict, or model usage",
                                      " ".join(st["problems"]))
                    self._next_refuses(f"lacks a valid {field}")
                    self.rewrite_record(sid, lambda rec: rec.update({field: good}))
                    self.assertEqual(self.states()[sid]["state"], "DONE")
        self.next_ruling()
        self.assertEqual(self.review(ids=[self.members[2]["shard_id"]]), 0, self.stdout)

    def test_site_terminal_command_fields(self):
        # Ari's four reproductions on 3c84363, each now refused in words
        self.assertEqual(self.review(ids=[self.ids[0]]), 0, self.stdout)
        cases = (("model_calls", True, "model_calls True does not rederive"),
                 ("model_calls", 1.0, "model_calls 1.0 does not rederive"),
                 ("cli_invocations", True, "cli_invocations True does not rederive"),
                 ("cli_invocations", 1.0, "cli_invocations 1.0 does not rederive"),
                 ("call_ceiling", 1.0, "call_ceiling 1.0 is not the exact number"),
                 ("call_ceiling", True, "call_ceiling True is not the exact number"),
                 ("attempts_allowed", 1.0, "attempts_allowed 1.0 is not the exact integer"),
                 ("attempts_allowed", True, "attempts_allowed True is not the exact integer"))
        for field, bad, needle in cases:
            with self.subTest(field=field, value=bad):
                good = canon.load_json(self.terminal_file())[field]
                self.rewrite_terminal(lambda cmd: cmd.update({field: bad}))
                cmds = run_reviewer_a.command_states(self.a)
                self.assertTrue(any(needle in p for p in cmds[0]["problems"]), cmds)
                self._next_refuses(needle)
                self.rewrite_terminal(lambda cmd: cmd.update({field: good}))
                self.assertEqual(run_reviewer_a.command_states(self.a)[0]["problems"], [])
        self.next_ruling()
        self.assertEqual(self.review(ids=[self.members[2]["shard_id"]]), 0, self.stdout)

    def _entry(self, index, mutate):
        def edit(cmd):
            mutate(cmd["shards"][index])
        self.rewrite_terminal(edit)

    def test_site_not_run_and_fail_entries(self):
        self.queue.append(GovernedShardSession(response="{}"))
        self.assertEqual(self.review(), 1)
        cmd = canon.load_json(self.terminal_file())
        self.assertEqual([s["result"] for s in cmd["shards"]], ["FAIL", "NOT_RUN"])
        fail_sid, not_run_sid = cmd["shards"][0]["shard_id"], cmd["shards"][1]["shard_id"]
        for field, bad in (("model_calls", 0.0), ("model_calls", False),
                           ("cli_invocations", 0.0), ("cli_invocations", False)):
            with self.subTest(entry="NOT_RUN", field=field, value=bad):
                good = canon.load_json(self.terminal_file())["shards"][1][field]
                self._entry(1, lambda e: e.update({field: bad}))
                needle = f"lists {not_run_sid} as NOT_RUN with calls or invocations"
                cmds = run_reviewer_a.command_states(self.a)
                self.assertTrue(any(needle in p for p in cmds[0]["problems"]), cmds)
                self._next_refuses(needle)
                self._entry(1, lambda e: e.update({field: good}))
        for field, bad in (("model_calls", True), ("model_calls", 1.0),
                           ("cli_invocations", True), ("cli_invocations", 1.0)):
            with self.subTest(entry="FAIL", field=field, value=bad):
                good = canon.load_json(self.terminal_file())["shards"][0][field]
                # the shard record stays as the harness wrote it: the entry
                # alone is edited, so the disagreement and the type are both named
                self._entry(0, lambda e: e.update({field: bad}))
                needle = f"lists {fail_sid} as FAIL with more than the one call"
                cmds = run_reviewer_a.command_states(self.a)
                self.assertTrue(any(needle in p for p in cmds[0]["problems"]), cmds)
                self.assertTrue(any(f"with {field} {bad!r}" in p
                                    for p in cmds[0]["problems"]), cmds)
                # the shard side names the disagreement first (the record's
                # exact count against the entry's lookalike); either way the
                # next command refuses before any session
                self.assertEqual(self.states()[fail_sid]["state"], "CORRUPT")
                self._next_refuses("review refused")
                self._entry(0, lambda e: e.update({field: good}))
        self.assertEqual(run_reviewer_a.command_states(self.a)[0]["problems"], [])

    def test_site_fail_record_counts(self):
        """Isolated pass 8, finding 1: a FAIL record's counts were held to
        the listing by value equality alone. The record's lookalike against
        the listing's integer is a disagreement on both sides, the FAIL
        record's own counts are bound to exact integers of at most one
        call, and the next command refuses before any session."""
        self.queue.append(GovernedShardSession(response="{}"))
        self.assertEqual(self.review(), 1)
        cmd = canon.load_json(self.terminal_file())
        self.assertEqual([s["result"] for s in cmd["shards"]], ["FAIL", "NOT_RUN"])
        sid = cmd["shards"][0]["shard_id"]
        original_path = cmd["shards"][0]["record_path"]
        for field, bad in (("model_calls", True), ("model_calls", 1.0),
                           ("cli_invocations", True), ("cli_invocations", 1.0)):
            with self.subTest(field=field, value=bad):
                good = canon.load_json(self.record_file(sid))[field]
                listing = canon.load_json(self.terminal_file())["shards"][0][field]
                # the record carries the lookalike; the listing keeps the
                # integer the harness wrote (fix_terminal would copy it over)
                new_sha = self.rewrite_record(sid, lambda rec: rec.update({field: bad}),
                                              fix_terminal=False)
                name = os.path.basename(self.record_file(sid))

                def point(c):
                    c["shards"][0]["record_sha256"] = new_sha
                    c["shards"][0]["record_path"] = f"{run_reviewer_a.RUN_RECORDS_DIR}/{name}"
                    c["shards"][0][field] = listing
                self.rewrite_terminal(point)
                st = self.states()[sid]
                self.assertEqual(st["state"], "CORRUPT", st)
                self.assertIn("the terminal command record disagrees with the shard record",
                              st["problems"])
                self.assertIn("a FAIL record carries counts that are not exact integers "
                              "of at most one call", st["problems"])
                cmds = run_reviewer_a.command_states(self.a)
                self.assertTrue(any("disagrees with the shard record" in p
                                    for p in cmds[0]["problems"]), cmds)
                self.assertTrue(any("not exact integers of at most one call" in p
                                    for p in cmds[0]["problems"]), cmds)
                self._next_refuses("review refused")
                # restoring the value restores the original bytes and name;
                # the listing's record_path is restored with it
                self.rewrite_record(sid, lambda rec: rec.update({field: good}))
                self.rewrite_terminal(lambda c: c["shards"][0].update(
                    record_path=original_path))
                self.assertEqual(self.states()[sid]["state"], "FAIL", self.states()[sid])
        self.assertEqual(run_reviewer_a.command_states(self.a)[0]["problems"], [])
        # the same lookalike on both sides is named by the listing's own check
        self.rewrite_record(sid, lambda rec: rec.update({"model_calls": True}))
        st = self.states()[sid]
        self.assertEqual(st["state"], "CORRUPT", st)
        cmds = run_reviewer_a.command_states(self.a)
        self.assertTrue(any(f"lists {sid} with model_calls True" in p
                            for p in cmds[0]["problems"]), cmds)
        self._next_refuses("review refused")

    def test_site_non_done_record_attempt_limit(self):
        """Isolated pass 9, finding 1: a non-DONE record's attempts_allowed
        is held only by the record-versus-reservation loop, which compared
        by value; as canonical bytes the lookalike is a disagreement, on the
        shard side and the command side, and the next command refuses."""
        self.queue.append(GovernedShardSession(response="{}"))
        self.assertEqual(self.review(), 1)
        cmd = canon.load_json(self.terminal_file())
        self.assertEqual([s["result"] for s in cmd["shards"]], ["FAIL", "NOT_RUN"])
        sid = cmd["shards"][0]["shard_id"]
        original_path = cmd["shards"][0]["record_path"]
        for bad in (True, 1.0):
            with self.subTest(value=bad):
                new_sha = self.rewrite_record(sid, lambda rec: rec.update(attempts_allowed=bad),
                                              fix_terminal=False)
                name = os.path.basename(self.record_file(sid))
                self.rewrite_terminal(lambda c: c["shards"][0].update(
                    record_sha256=new_sha, record_path=f"{run_reviewer_a.RUN_RECORDS_DIR}/{name}"))
                st = self.states()[sid]
                self.assertEqual(st["state"], "CORRUPT", st)
                self.assertIn("reservation and record disagree on attempts_allowed",
                              st["problems"])
                # the loop is a shard-side check; the next command refuses on
                # the shard side before any session
                self._next_refuses("disagree on attempts_allowed")
                self.rewrite_record(sid, lambda rec: rec.update(attempts_allowed=REVIEW_ATTEMPTS),
                                    fix_terminal=False)
                self.rewrite_terminal(lambda c: c["shards"][0].update(
                    record_sha256=RECORD_SHA_OF(self.record_file(sid)),
                    record_path=original_path))
                self.assertEqual(self.states()[sid]["state"], "FAIL", self.states()[sid])
        self.assertEqual(run_reviewer_a.command_states(self.a)[0]["problems"], [])

    def test_site_unattested_entry(self):
        real = self.saved["write_review_record"]

        def writer(directory, prefix, record):
            if directory.endswith(run_reviewer_a.RUN_RECORDS_DIR):
                raise OSError("record store down")
            return real(directory, prefix, record)
        run_reviewer_a.write_review_record = writer
        self.queue.append(RaisingSession(RuntimeError("cli died")))
        self.review_raises(OSError, ids=[self.ids[0]])
        run_reviewer_a.write_review_record = real
        sid = self.ids[0]
        self.assertEqual(self.command_record()["shards"][0]["result"], "UNATTESTED")
        self.assertEqual(run_reviewer_a.command_states(self.a)[0]["problems"], [])
        for field, bad in (("model_calls", True), ("model_calls", 1.0),
                           ("cli_invocations", True), ("cli_invocations", 1.0)):
            with self.subTest(field=field, value=bad):
                good = canon.load_json(self.terminal_file())["shards"][0][field]
                self._entry(0, lambda e: e.update({field: bad}))
                needle = f"lists {sid} as UNATTESTED with more than the one call"
                cmds = run_reviewer_a.command_states(self.a)
                self.assertTrue(any(needle in p for p in cmds[0]["problems"]), cmds)
                self._next_refuses(needle)
                self._entry(0, lambda e: e.update({field: good}))
        self.assertEqual(run_reviewer_a.command_states(self.a)[0]["problems"], [])


class OutputsDirectoryFsyncFailure(_Root):
    """Finding 5."""

    def test_fsync_failure_after_the_link_quarantines_the_output(self):
        outputs = self.path(run_reviewer_a.OUTPUTS_DIR)
        real_fsync = os.fsync
        state = {"tripped": 0}

        def fsync(fd):
            st = os.fstat(fd)
            if os.path.isdir(outputs) and (st.st_dev, st.st_ino) == (
                    os.stat(outputs).st_dev, os.stat(outputs).st_ino) and \
                    os.path.lexists(os.path.join(outputs, f"{self.ids[0]}.json")):
                state["tripped"] += 1
                raise OSError(5, "Input/output error")
            return real_fsync(fd)
        os.fsync = fsync
        try:
            self.assertEqual(self.review(ids=[self.ids[0]]), 1)
        finally:
            os.fsync = real_fsync
        self.assertEqual(state["tripped"], 1)
        rec = self.record(self.ids[0])
        self.assertEqual((rec["result"], rec["phase"]), ("FAIL", "install"), rec["error"])
        self.assertIn("could not be fsynced", rec["error"])
        self.assertIn("moved to REFUSED-output-", rec["error"])
        self.assertIsNone(rec["output_sha256"])
        self.assertEqual([n for n in os.listdir(outputs) if not n.startswith(".")], [])
        quarantined = [n for n in os.listdir(self.a) if n.startswith("REFUSED-output-")]
        self.assertEqual(len(quarantined), 1, quarantined)
        with open(self.path(quarantined[0]), "rb") as f:
            self.assertIn(b'"foundry-pass-2-review-output/', f.read()[:120])
        st = self.states()[self.ids[0]]
        self.assertEqual((st["state"], st["problems"]), ("FAIL", []))
        self.assertEqual(self.command_record()["shards"][0]["result"], "FAIL")
        # the quarantine refuses the next command until a maintainer looks
        self.next_ruling()
        self.assert_refused_before_reservation("quarantined bytes from a refused install",
                                               ids=[self.ids[1]])


if __name__ == "__main__":
    unittest.main()
