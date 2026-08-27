"""Run the release gate over fixed reviewer outputs. From experiments/foundry-pass-2:

    python3 tools/run_gate.py

Inputs (all must exist; anything missing is a FAIL/MISSING gate, the report
still ships for the record, and the exit code is 1):
  out/reviewer-a/{reviewer-identity.json, outputs/*.json, run-records/}
  out/reviewer-b/{reviewer-identity.json, outputs/*.json[, failed-units.json]}
  out/gate/control-grading.json   (evaluator's grader output after reveal)
The gate runs twice; the second pass must reproduce the first byte for byte
(class-1 replay) before the release manifest can record issued: true.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS2 = os.path.dirname(HERE)
sys.path.insert(0, PASS2)
sys.path.insert(0, HERE)

from engine import canon, gate  # noqa: E402
from adapters.ecfr_pass1.adapter import EcfrPass1Adapter  # noqa: E402
from run_reviewer_a import schema_validator  # noqa: E402

OUT = os.path.join(PASS2, "out")
THRESHOLDS = {"coverage_units_min": 30, "acceptance_rate_min": 0.5}  # brief 9
GATE_FILES = ("partition.json", "exclusions-appendix.json",
              "release-report.json", "release-candidate.json")


def extra_failed_units(reviewer_dir):
    failed = set()
    records = os.path.join(reviewer_dir, "run-records")
    if os.path.isdir(records):
        for name in os.listdir(records):
            rec = canon.load_json(os.path.join(records, name))
            if rec.get("verdict") != "fixed":
                failed.add(rec["shard_id"].replace("shard-", ""))
    extra = os.path.join(reviewer_dir, "failed-units.json")
    if os.path.isfile(extra):
        failed |= set(canon.load_json(extra))
    return sorted(failed)


def _bound(path, base=OUT):
    if not os.path.isfile(path):
        return {"path": os.path.relpath(path, base), "sha256": None,
                "status": "MISSING"}
    return {"path": os.path.relpath(path, base), "sha256": canon.file_sha256(path)}


def _optional_json(path):
    return canon.load_json(path) if os.path.isfile(path) else None


def run_once():
    bundle_path = os.path.join(OUT, "review-input-bundle.json")
    bundle = canon.load_json(bundle_path)
    review = canon.load_json(os.path.join(OUT, "review-universe.json"))
    natural = canon.load_json(os.path.join(OUT, "sealed", "natural-universe.json"))
    manifest = canon.load_json(os.path.join(OUT, "shard-manifest.json"))
    a_dir, b_dir = os.path.join(OUT, "reviewer-a"), os.path.join(OUT, "reviewer-b")
    id_a_path = os.path.join(a_dir, "reviewer-identity.json")
    id_b_path = os.path.join(b_dir, "reviewer-identity.json")
    bindings = {
        "contract_sha256": bundle["bindings"]["reviewer_contract"]["sha256"],
        "review_input_bundle_sha256": canon.file_sha256(bundle_path),
        "shard_manifest_sha256": bundle["shard_manifest"]["sha256"],
        "reviewer_a_identity_sha256":
            canon.file_sha256(id_a_path) if os.path.isfile(id_a_path) else "MISSING",
        "reviewer_b_identity_sha256":
            canon.file_sha256(id_b_path) if os.path.isfile(id_b_path) else "MISSING",
    }
    grading_path = os.path.join(OUT, "gate", "control-grading.json")
    report = gate.run_gate(
        OUT, review, natural, manifest, bindings,
        os.path.join(a_dir, "outputs"), os.path.join(b_dir, "outputs"),
        _optional_json(id_a_path), _optional_json(id_b_path),
        _optional_json(grading_path),
        extra_failed_units(a_dir), extra_failed_units(b_dir),
        EcfrPass1Adapter().unit_ids(), THRESHOLDS, schema_validator)
    return report, bundle, id_a_path, id_b_path, grading_path


def main():
    report, bundle, id_a_path, id_b_path, grading_path = run_once()
    first = {n: canon.file_sha256(os.path.join(OUT, "gate", n)) for n in GATE_FILES}
    run_once()
    second = {n: canon.file_sha256(os.path.join(OUT, "gate", n)) for n in GATE_FILES}
    replay = gate.status(gate.PASS if first == second else gate.FAIL,
                         first_pass=first, second_pass=second)
    bound = {
        "ratified_brief": bundle["bindings"]["brief"],
        "review_input_bundle": _bound(os.path.join(OUT, "review-input-bundle.json")),
        "review_universe": _bound(os.path.join(OUT, "review-universe.json")),
        "natural_universe_sealed": _bound(os.path.join(OUT, "sealed", "natural-universe.json")),
        "reviewer_a_identity": _bound(id_a_path),
        "reviewer_b_identity": _bound(id_b_path),
        "reviewer_a_outputs": report["appendices"]["reviewer_a_outputs"],
        "reviewer_b_outputs": report["appendices"]["reviewer_b_outputs"],
        "partition": report["appendices"]["partition"],
        "exclusions_appendix": report["appendices"]["exclusions"],
        "release_report": _bound(os.path.join(OUT, "gate", "release-report.json")),
        "release_candidate": report["appendices"]["release_candidate"],
        "control_grading": _bound(grading_path),
    }
    manifest_sha, issued = gate.release_manifest(OUT, bound, report, replay)
    s = report["decision_summary"]
    print("natural:", s["natural_release_universe"], "accepted:",
          s["unanimously_accepted_natural"], "rate:", s["acceptance_rate_natural"],
          "units:", s["units_with_at_least_one_accepted_natural_claim"])
    gates = dict(report["gates"]); gates["class_1_replay"] = replay
    print("gates:", {k: v["status"] for k, v in gates.items()})
    print("reconciliation:", report["partition_counts"]["reconciliation"])
    print("RELEASE_MANIFEST_SHA256:", manifest_sha, "issued:", issued)
    if not issued:
        print("NO RELEASE CANDIDATE: measured attempt only; gates not PASS:",
              [k for k, v in gates.items() if v["status"] != "PASS"])
        sys.exit(1)


if __name__ == "__main__":
    main()
