"""The release gate: unanimity merge, deterministic partition, release
report, release candidate, release manifest (brief sections 4a, 6, 6a, 9).

Every hard gate is a typed status: PASS, FAIL, PENDING, or MISSING. A
release candidate issues only when every required gate is exactly PASS,
including control grading and class-1 replay. Anything else is a measured
attempt with a report for the record and no candidate.

Class-1: same universe + same reviewer outputs => same partition and report
bytes. No clock, no randomness, no adjudication, no repair.

The gate validates its own inputs (Ari review 2026-08-27): every reviewer
output file must pass the bound schema validator, carry the bound contract,
bundle, shard-manifest, and identity digests, cover its shard exactly once,
and preserve every declared record digest. Both reviewer identity records
must exist, carry the contract's required fields, and show every leak
probe passed before the first real review.
"""

import os

from . import canon

GATE_VERSION = "foundry-release-gate/experimental-v0.1"
PASS, FAIL, PENDING, MISSING = "PASS", "FAIL", "PENDING", "MISSING"

REASONS = (
    "missing-disposition",
    "rejected-by-both",
    "rejected-by-a",
    "rejected-by-b",
    "correction-proposed",
    "abstention",
    "payload-non-equivalent",
    "anchor-mismatch",
)

IDENTITY_REQUIRED_FIELDS = (
    "reviewer_role", "operator_lineage", "model_provider", "model_id",
    "model_version_or_build", "system_prompt_sha256",
    "task_prompt_template_sha256", "output_schema_sha256", "harness_sha256",
    "parser_sha256", "tool_allowlist_sha256", "settings_sources_sha256",
    "configuration_sha256", "environment_boundary_sha256",
    "leak_probe_transcript_sha256", "session_ids_sha256",
)
REQUIRED_GATES = (
    "partition_reconciliation", "reviewer_a_identity", "reviewer_b_identity",
    "reviewer_output_validity", "control_grading", "coverage_units_min",
    "acceptance_rate_min", "class_1_replay",
)


class GateError(Exception):
    """Hard stop: the gate cannot even produce a record."""


def status(state, **detail):
    return {"status": state, **detail}


def check_identity(identity, role):
    if identity is None:
        return status(MISSING, role=role)
    missing = [f for f in IDENTITY_REQUIRED_FIELDS if not identity.get(f)]
    probes = identity.get("leak_probes") or []
    failed_probes = [p.get("id") for p in probes if not p.get("pass")]
    problems = []
    if missing:
        problems.append(f"missing fields: {missing}")
    if identity.get("reviewer_role") != role:
        problems.append("role mismatch")
    if not identity.get("bound_before_first_real_review"):
        problems.append("not bound before first real review")
    if not probes:
        problems.append("no leak probe record")
    if failed_probes:
        problems.append(f"failed probes: {failed_probes}")
    return status(PASS if not problems else FAIL, role=role,
                  problems=problems)


def load_outputs(outputs_dir, expected_bindings, shard_manifest, universe,
                 validator):
    """Validate and load one reviewer's fixed outputs.

    Returns (dispositions by artifact_id, per-file records, failed unit
    ids, problems). A file that fails any check contributes no dispositions
    and marks its shard's unit as a review-execution failure for this
    reviewer; the problem list feeds the reviewer_output_validity gate."""
    shards = {m["shard_id"]: m for m in shard_manifest["shards"]}
    dispositions = {}
    files = []
    failed_units = set()
    problems = []
    seen_shards = set()
    names = sorted(n for n in os.listdir(outputs_dir) if n.endswith(".json")) \
        if os.path.isdir(outputs_dir) else []
    for name in names:
        path = os.path.join(outputs_dir, name)
        output = canon.load_json(path)
        file_problems = []
        ok, _ = validator(output)
        if not ok:
            file_problems.append("schema")
        for field, expected in expected_bindings.items():
            if output.get(field) != expected:
                file_problems.append(f"{field}-mismatch")
        member = shards.get(output.get("shard_id"))
        if member is None:
            file_problems.append("unknown-shard")
        elif output["shard_id"] in seen_shards:
            file_problems.append("duplicate-shard-output")
        else:
            seen_shards.add(output["shard_id"])
            ids = [d.get("artifact_id") for d in output.get("dispositions", [])]
            if sorted(ids) != sorted(member["artifact_ids"]) or \
                    len(set(ids)) != len(ids):
                file_problems.append("completeness")
            for d in output.get("dispositions", []):
                entry = universe.get(d.get("artifact_id"))
                if entry is None or \
                        d.get("record_sha256") != entry["record_sha256"] or \
                        d.get("claim_payload_sha256") != entry["claim_payload_sha256"] or \
                        d.get("normalized_support_anchor_set_sha256") != \
                        entry["normalized_support_anchor_set_sha256"]:
                    file_problems.append("digest-not-preserved")
                    break
        files.append({"path": name, "sha256": canon.file_sha256(path),
                      "shard_id": output.get("shard_id"),
                      "problems": sorted(set(file_problems))})
        if file_problems:
            if member is not None:
                failed_units.add(member["unit_id"])
            problems.append(f"{name}: {sorted(set(file_problems))}")
            continue
        for d in output["dispositions"]:
            dispositions[d["artifact_id"]] = d
    for member in shard_manifest["shards"]:
        if member["shard_id"] not in seen_shards:
            failed_units.add(member["unit_id"])
            problems.append(f"{member['shard_id']}: no fixed output")
    return dispositions, files, sorted(failed_units), problems


def _bound_accept(d, entry):
    return (d is not None and d["verdict"] == "accept" and
            d["record_sha256"] == entry["record_sha256"] and
            d["claim_payload_sha256"] == entry["claim_payload_sha256"] and
            d["normalized_support_anchor_set_sha256"] ==
            entry["normalized_support_anchor_set_sha256"])


def classify(entry, a, b, failed_units):
    if entry["unit_id"] in failed_units:
        return "failed", "review-execution-failure"
    if a is None or b is None:
        return "excluded", "missing-disposition"
    if _bound_accept(a, entry) and _bound_accept(b, entry):
        return "accepted", None
    va, vb = a["verdict"], b["verdict"]
    if va == "reject" and vb == "reject":
        return "excluded", "rejected-by-both"
    if va == "reject":
        return "excluded", "rejected-by-a"
    if vb == "reject":
        return "excluded", "rejected-by-b"
    if "correct" in (va, vb):
        return "excluded", "correction-proposed"
    if "abstain" in (va, vb):
        return "excluded", "abstention"
    for d in (a, b):
        if d["claim_payload_sha256"] != entry["claim_payload_sha256"] or \
                d["record_sha256"] != entry["record_sha256"]:
            return "excluded", "payload-non-equivalent"
    return "excluded", "anchor-mismatch"


def run_gate(out_dir, review_listing, natural_listing, shard_manifest,
             bindings, outputs_a, outputs_b, identity_a, identity_b,
             control_grading, extra_failed_a, extra_failed_b, unit_ids_all,
             thresholds, validator):
    """Merge + partition + report. Writes out/gate/*. Returns the report.

    bindings: {"contract_sha256", "review_input_bundle_sha256",
               "shard_manifest_sha256", "reviewer_a_identity_sha256",
               "reviewer_b_identity_sha256"}
    control_grading: the evaluator's grading result dict, or None.
    """
    gate_dir = os.path.join(out_dir, "gate")
    control_ids = set(natural_listing["control_artifact_ids"])
    natural_ids = {r["artifact_id"] for r in natural_listing["records"]}
    universe = {r["artifact_id"]: r for r in review_listing["records"]}
    if set(universe) != natural_ids | control_ids:
        raise GateError("review universe != natural + controls")

    common = {k: bindings[k] for k in (
        "contract_sha256", "review_input_bundle_sha256", "shard_manifest_sha256")}
    a, files_a, failed_a, problems_a = load_outputs(
        outputs_a, dict(common, reviewer_identity_sha256=bindings["reviewer_a_identity_sha256"]),
        shard_manifest, universe, validator)
    b, files_b, failed_b, problems_b = load_outputs(
        outputs_b, dict(common, reviewer_identity_sha256=bindings["reviewer_b_identity_sha256"]),
        shard_manifest, universe, validator)
    failed_a = sorted(set(failed_a) | set(extra_failed_a))
    failed_b = sorted(set(failed_b) | set(extra_failed_b))
    failed_units = set(failed_a) | set(failed_b)

    accepted, excluded, failed = [], [], []
    rows = {}
    for artifact_id in sorted(universe):
        entry = universe[artifact_id]
        outcome, reason = classify(entry, a.get(artifact_id),
                                   b.get(artifact_id), failed_units)
        rows[artifact_id] = {"artifact_id": artifact_id,
                             "unit_id": entry["unit_id"], "outcome": outcome,
                             "reason": reason, "reviewer_a": a.get(artifact_id),
                             "reviewer_b": b.get(artifact_id)}
        {"accepted": accepted, "excluded": excluded,
         "failed": failed}[outcome].append(artifact_id)

    sets = [set(accepted), set(excluded), set(failed)]
    if sum(len(s) for s in sets) != len(universe) or \
            set.union(*sets) != set(universe) or \
            any(s & t for i, s in enumerate(sets) for t in sets[i + 1:]):
        raise GateError("partition mismatch: hard stop")
    partition = {
        "artifact_version": GATE_VERSION + "/partition",
        "review_universe_count": len(universe),
        "unanimously_accepted": accepted,
        "excluded_by_reason": {
            reason: sorted(i for i in excluded if rows[i]["reason"] == reason)
            for reason in REASONS},
        "review_execution_failures": failed,
        "reconciliation": f"{len(universe)} = {len(accepted)} + "
                          f"{len(excluded)} + {len(failed)}",
    }
    partition_sha = canon.write_canonical(
        os.path.join(gate_dir, "partition.json"), partition)

    # --- release projection: controls removed, natural universe only -----
    nat_accepted = sorted(i for i in accepted if i in natural_ids)
    nat_total = len(natural_ids)
    units_with_accept = sorted({universe[i]["unit_id"] for i in nat_accepted})
    per_unit = {u: {"natural": 0, "accepted": 0, "excluded": 0, "failed": 0}
                for u in unit_ids_all}
    for i in natural_ids:
        p = per_unit.setdefault(universe[i]["unit_id"], {
            "natural": 0, "accepted": 0, "excluded": 0, "failed": 0})
        p["natural"] += 1
        p[rows[i]["outcome"]] += 1
    agreement = {}
    for u in per_unit:
        ids = [i for i in natural_ids if universe[i]["unit_id"] == u
               and rows[i]["outcome"] != "failed"]
        agree = sum(1 for i in ids if a.get(i) and b.get(i) and
                    a[i]["verdict"] == b[i]["verdict"])
        agreement[u] = {"compared": len(ids), "agreed": agree}
    reason_counts = {r: len(v) for r, v in partition["excluded_by_reason"].items()}
    nat_reason_counts = {r: sum(1 for i in v if i in natural_ids)
                         for r, v in partition["excluded_by_reason"].items()}

    def abstentions(d):
        return sum(1 for i in natural_ids
                   if d.get(i) and d[i]["verdict"] == "abstain")

    coverage_units = len(units_with_accept)
    acceptance_rate = (len(nat_accepted) / nat_total) if nat_total else 0.0
    if control_grading is None:
        grading = status(MISSING)
    else:
        grading = status(PASS if control_grading.get("hard_gate_result") == "PASS"
                         else FAIL, result=control_grading.get("hard_gate_result"),
                         metrics=control_grading.get("metrics"))
    gates = {
        "partition_reconciliation": status(PASS, reconciliation=partition["reconciliation"]),
        "reviewer_a_identity": check_identity(identity_a, "reviewer_a"),
        "reviewer_b_identity": check_identity(identity_b, "reviewer_b"),
        "reviewer_output_validity": status(
            PASS if not (problems_a or problems_b) else FAIL,
            reviewer_a=problems_a, reviewer_b=problems_b),
        "control_grading": grading,
        "coverage_units_min": status(
            PASS if coverage_units >= thresholds["coverage_units_min"] else FAIL,
            required=thresholds["coverage_units_min"], observed=coverage_units),
        "acceptance_rate_min": status(
            PASS if acceptance_rate >= thresholds["acceptance_rate_min"] else FAIL,
            required=thresholds["acceptance_rate_min"],
            observed=round(acceptance_rate, 4)),
        "class_1_replay": status(PENDING, note="verified by the runner's "
                                 "second pass; bound in the release manifest"),
    }
    in_report_pass = all(gates[g]["status"] == PASS for g in REQUIRED_GATES
                         if g != "class_1_replay")
    report = {
        "artifact_version": GATE_VERSION + "/release-report",
        "decision_summary": {
            "natural_release_universe": nat_total,
            "unanimously_accepted_natural": len(nat_accepted),
            "excluded_natural": sum(nat_reason_counts.values()),
            "failed_natural": sum(1 for i in natural_ids if rows[i]["outcome"] == "failed"),
            "controls_in_review_universe": len(control_ids),
            "controls_note": "controls removed before this projection; graded "
                             "separately after oracle reveal; they count toward "
                             "no gate here",
            "units_with_at_least_one_accepted_natural_claim": coverage_units,
            "units_total": len(unit_ids_all),
            "acceptance_rate_natural": round(acceptance_rate, 4),
        },
        "issuance": {
            "all_in_report_gates_pass": in_report_pass,
            "not_pass": sorted(g for g in REQUIRED_GATES
                               if gates[g]["status"] != PASS),
            "note": "a release candidate issues only when every required "
                    "gate, including class_1_replay in the manifest, is PASS",
        },
        "gates": gates,
        "coverage_per_unit": dict(sorted(per_unit.items())),
        "agreement_per_unit": dict(sorted(agreement.items())),
        "concept_coverage": "not computed by the engine: the Pass 1 concept "
                            "reference is the evaluator-held 40-question "
                            "bank, not a list in the canonical index; "
                            "evaluator grades it after reveal",
        "partition_counts": {"accepted": len(accepted),
                             "excluded_by_reason": reason_counts,
                             "review_execution_failures": len(failed),
                             "reconciliation": partition["reconciliation"]},
        "honest_statistics": {
            "excluded_by_reason_natural": nat_reason_counts,
            "abstentions": {"reviewer_a": abstentions(a),
                            "reviewer_b": abstentions(b)},
            "review_execution_failures_by_reviewer": {
                "reviewer_a_units": failed_a, "reviewer_b_units": failed_b},
            "release_review_duration": "reported by the maintainer per release",
        },
        "risk_ranked_exceptions": [
            {"reason": r, "count": nat_reason_counts[r]}
            for r in REASONS if nat_reason_counts[r]],
        "provenance_label_for_accepted": "machine-unanimous",
        "appendices": {
            "partition": {"path": "gate/partition.json", "sha256": partition_sha},
            "reviewer_a_outputs": files_a,
            "reviewer_b_outputs": files_b,
        },
    }
    appendix_sha = canon.write_canonical(
        os.path.join(gate_dir, "exclusions-appendix.json"),
        {"artifact_version": GATE_VERSION + "/exclusions",
         "records": [rows[i] for i in excluded + failed]})
    report["appendices"]["exclusions"] = {
        "path": "gate/exclusions-appendix.json", "sha256": appendix_sha}
    candidate = {
        "artifact_version": GATE_VERSION + "/experimental-release-candidate",
        "standing": "NOT A RELEASE CANDIDATE unless the release manifest "
                    "records issued: true; experimental; not promoted; every "
                    "claim labeled machine-unanimous",
        "claims": [
            {"artifact_id": i, **universe[i],
             "provenance": {"label": "machine-unanimous",
                            "reviewer_a_output_sha256s": [f["sha256"] for f in files_a],
                            "reviewer_b_output_sha256s": [f["sha256"] for f in files_b]}}
            for i in nat_accepted],
    }
    candidate_sha = canon.write_canonical(
        os.path.join(gate_dir, "release-candidate.json"), candidate)
    report["appendices"]["release_candidate"] = {
        "path": "gate/release-candidate.json", "sha256": candidate_sha}
    canon.write_canonical(os.path.join(gate_dir, "release-report.json"), report)
    return report


def release_manifest(out_dir, bound, report, replay_status):
    """Bind everything under one digest (6a) and decide issuance: every
    required gate exactly PASS, with class_1_replay taken from the runner's
    second pass. Returns (manifest sha256, issued)."""
    gates = dict(report["gates"])
    gates["class_1_replay"] = replay_status
    issued = all(gates[g]["status"] == PASS for g in REQUIRED_GATES) and \
        all(isinstance(v, dict) and v.get("sha256") for v in bound.values()
            if not isinstance(v, list))
    manifest = {"artifact_version": GATE_VERSION + "/release-manifest",
                "binds": bound,
                "gates": {g: gates[g]["status"] for g in REQUIRED_GATES},
                "issued": issued}
    sha = canon.write_canonical(
        os.path.join(out_dir, "gate", "release-manifest.json"), manifest)
    return sha, issued
