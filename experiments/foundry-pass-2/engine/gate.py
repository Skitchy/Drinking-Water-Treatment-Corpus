"""The release gate: unanimity merge, deterministic partition, release
report, release candidate, release manifest (brief sections 4a, 6, 6a, 9).

Class-1: same universe + same reviewer outputs => same partition and report
bytes. No clock, no randomness, no adjudication, no repair.

Inputs are plain dicts and paths; the gate never reads adapter or evaluator
trees by name.
"""

import os

from . import canon

GATE_VERSION = "foundry-release-gate/experimental-v0.1"

# Exclusion reason codes, brief 4a, in the priority order applied when more
# than one would fit (the most fundamental failure names the record).
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


class GateError(Exception):
    """Hard stop (partition mismatch or bound-input drift)."""


def load_outputs(outputs_dir):
    """artifact_id -> disposition, from every schema-valid fixed output in a
    directory; duplicates across shards are a hard stop."""
    dispositions = {}
    digests = []
    for name in sorted(os.listdir(outputs_dir)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(outputs_dir, name)
        digests.append({"path": name, "sha256": canon.file_sha256(path)})
        for d in canon.load_json(path)["dispositions"]:
            if d["artifact_id"] in dispositions:
                raise GateError(f"duplicate disposition {d['artifact_id']}")
            dispositions[d["artifact_id"]] = d
    return dispositions, digests


def _bound_accept(d, entry):
    return (d is not None and d["verdict"] == "accept" and
            d["record_sha256"] == entry["record_sha256"] and
            d["claim_payload_sha256"] == entry["claim_payload_sha256"] and
            d["normalized_support_anchor_set_sha256"] ==
            entry["normalized_support_anchor_set_sha256"])


def classify(entry, a, b, failed_units):
    """One record -> ('accepted'|'excluded'|'failed', reason)."""
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
    # both said accept but at least one over different digests
    for d in (a, b):
        if d["claim_payload_sha256"] != entry["claim_payload_sha256"] or \
                d["record_sha256"] != entry["record_sha256"]:
            return "excluded", "payload-non-equivalent"
    return "excluded", "anchor-mismatch"


def run_gate(out_dir, review_listing, natural_listing, outputs_a, outputs_b,
             failed_units_a, failed_units_b, unit_ids_all, thresholds):
    """Merge + partition + report. Writes out/gate/*. Returns the report."""
    gate_dir = os.path.join(out_dir, "gate")
    a, digests_a = load_outputs(outputs_a)
    b, digests_b = load_outputs(outputs_b)
    failed_units = set(failed_units_a) | set(failed_units_b)
    control_ids = set(natural_listing["control_artifact_ids"])
    natural_ids = {r["artifact_id"] for r in natural_listing["records"]}
    universe = {r["artifact_id"]: r for r in review_listing["records"]}
    if set(universe) != natural_ids | control_ids:
        raise GateError("review universe != natural + controls")
    unexpected = (set(a) | set(b)) - set(universe)
    if unexpected:
        raise GateError(f"dispositions outside the universe: "
                        f"{sorted(unexpected)[:5]}")

    accepted, excluded, failed = [], [], []
    rows = {}
    for artifact_id in sorted(universe):
        entry = universe[artifact_id]
        outcome, reason = classify(entry, a.get(artifact_id),
                                   b.get(artifact_id), failed_units)
        row = {"artifact_id": artifact_id, "unit_id": entry["unit_id"],
               "outcome": outcome, "reason": reason,
               "reviewer_a": a.get(artifact_id),
               "reviewer_b": b.get(artifact_id)}
        rows[artifact_id] = row
        {"accepted": accepted, "excluded": excluded,
         "failed": failed}[outcome].append(artifact_id)

    # --- partition reconciliation (4a): exactly once, sums exactly --------
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
    per_unit = {}
    for i in natural_ids:
        u = universe[i]["unit_id"]
        p = per_unit.setdefault(u, {"natural": 0, "accepted": 0,
                                    "excluded": 0, "failed": 0})
        p["natural"] += 1
        p[rows[i]["outcome"]] += 1
    for u in unit_ids_all:
        per_unit.setdefault(u, {"natural": 0, "accepted": 0,
                                "excluded": 0, "failed": 0})
    agreement = {}
    for u, p in per_unit.items():
        ids = [i for i in natural_ids if universe[i]["unit_id"] == u
               and rows[i]["outcome"] != "failed"]
        agree = sum(1 for i in ids if a.get(i) and b.get(i) and
                    a[i]["verdict"] == b[i]["verdict"])
        agreement[u] = {"compared": len(ids), "agreed": agree}
    reason_counts = {r: len(v) for r, v in partition["excluded_by_reason"].items()}
    nat_reason_counts = {
        r: sum(1 for i in v if i in natural_ids)
        for r, v in partition["excluded_by_reason"].items()}
    abst = lambda d: sum(1 for i in natural_ids if d.get(i) and d[i]["verdict"] == "abstain")  # noqa: E731

    coverage_units = len(units_with_accept)
    acceptance_rate = (len(nat_accepted) / nat_total) if nat_total else 0.0
    gates = {
        "partition_reconciliation": True,
        "coverage_units_min": {"required": thresholds["coverage_units_min"],
                               "observed": coverage_units,
                               "pass": coverage_units >= thresholds["coverage_units_min"]},
        "acceptance_rate_min": {"required": thresholds["acceptance_rate_min"],
                                "observed": round(acceptance_rate, 4),
                                "pass": acceptance_rate >= thresholds["acceptance_rate_min"]},
        "control_grading": "pending oracle reveal (evaluator); hard gate",
        "leak_probes_and_independence": "recorded in reviewer identity records; hard gate",
        "class_1_replay": "verified by re-running the gate over fixed inputs",
    }
    report = {
        "artifact_version": GATE_VERSION + "/release-report",
        "decision_summary": {
            "natural_release_universe": nat_total,
            "unanimously_accepted_natural": len(nat_accepted),
            "excluded_natural": sum(nat_reason_counts.values()),
            "failed_natural": sum(1 for i in natural_ids if rows[i]["outcome"] == "failed"),
            "controls_in_review_universe": len(control_ids),
            "controls_note": "controls removed before this projection; "
                             "graded separately after oracle reveal; they "
                             "count toward no gate here",
            "units_with_at_least_one_accepted_natural_claim": coverage_units,
            "units_total": len(unit_ids_all),
            "acceptance_rate_natural": round(acceptance_rate, 4),
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
            "abstentions": {"reviewer_a": abst(a), "reviewer_b": abst(b)},
            "review_execution_failures_by_reviewer": {
                "reviewer_a_units": sorted(failed_units_a),
                "reviewer_b_units": sorted(failed_units_b)},
            "release_review_duration": "reported by the maintainer per release",
        },
        "risk_ranked_exceptions": [
            {"reason": r, "count": nat_reason_counts[r]}
            for r in REASONS if nat_reason_counts[r]],
        "provenance_label_for_accepted": "machine-unanimous",
        "appendices": {
            "partition": {"path": "gate/partition.json", "sha256": partition_sha},
            "reviewer_a_outputs": digests_a,
            "reviewer_b_outputs": digests_b,
        },
    }
    exclusions = [rows[i] for i in excluded + failed]
    appendix_sha = canon.write_canonical(
        os.path.join(gate_dir, "exclusions-appendix.json"),
        {"artifact_version": GATE_VERSION + "/exclusions",
         "records": exclusions})
    report["appendices"]["exclusions"] = {
        "path": "gate/exclusions-appendix.json", "sha256": appendix_sha}
    candidate = {
        "artifact_version": GATE_VERSION + "/experimental-release-candidate",
        "standing": "experimental; not promoted; every claim labeled "
                    "machine-unanimous",
        "claims": [
            {"artifact_id": i, **universe[i],
             "provenance": {"label": "machine-unanimous",
                            "reviewer_a_output_sha256s": digests_a,
                            "reviewer_b_output_sha256s": digests_b}}
            for i in nat_accepted],
    }
    candidate_sha = canon.write_canonical(
        os.path.join(gate_dir, "release-candidate.json"), candidate)
    report["appendices"]["release_candidate"] = {
        "path": "gate/release-candidate.json", "sha256": candidate_sha,
        "issued": all(g.get("pass", True) for g in gates.values()
                      if isinstance(g, dict)),
        "note": "a candidate file is always written for the record; it is "
                "a release candidate only if every hard gate, including "
                "control grading, passes",
    }
    canon.write_canonical(os.path.join(gate_dir, "release-report.json"), report)
    return report


def release_manifest(out_dir, bound):
    """Bind everything under one digest (6a). `bound` is an ordered dict of
    name -> {path, sha256}; the manifest digest is what the maintainer's
    signature names."""
    manifest = {"artifact_version": GATE_VERSION + "/release-manifest",
                "binds": bound}
    sha = canon.write_canonical(
        os.path.join(out_dir, "gate", "release-manifest.json"), manifest)
    return sha
