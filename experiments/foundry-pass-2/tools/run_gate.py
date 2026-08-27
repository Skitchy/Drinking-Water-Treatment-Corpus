"""Run the release gate over fixed reviewer outputs. From experiments/foundry-pass-2:

    python3 tools/run_gate.py

Reviewer A outputs: out/reviewer-a/outputs/*.json (harness-fixed).
Reviewer B outputs: out/reviewer-b/outputs/*.json (Ari's lineage, delivered
by digest; run records alongside at out/reviewer-b/).
Units with a review-execution failure are read from each reviewer's run
records (verdict != fixed) and from out/reviewer-b/failed-units.json if
Ari's side reports any.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS2 = os.path.dirname(HERE)
sys.path.insert(0, PASS2)

from engine import canon, gate  # noqa: E402
from adapters.ecfr_pass1.adapter import EcfrPass1Adapter  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(PASS2, "..", ".."))
OUT = os.path.join(PASS2, "out")
THRESHOLDS = {"coverage_units_min": 30, "acceptance_rate_min": 0.5}  # brief 9


def failed_units(reviewer_dir):
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
    return {"path": os.path.relpath(path, base), "sha256": canon.file_sha256(path)}


def main():
    review = canon.load_json(os.path.join(OUT, "review-universe.json"))
    natural = canon.load_json(os.path.join(OUT, "sealed", "natural-universe.json"))
    a_dir, b_dir = os.path.join(OUT, "reviewer-a"), os.path.join(OUT, "reviewer-b")
    for d in (a_dir, b_dir):
        if not os.path.isdir(os.path.join(d, "outputs")):
            raise SystemExit(f"missing fixed outputs: {d}/outputs")
    report = gate.run_gate(
        OUT, review, natural, os.path.join(a_dir, "outputs"),
        os.path.join(b_dir, "outputs"), failed_units(a_dir), failed_units(b_dir),
        EcfrPass1Adapter().unit_ids(), THRESHOLDS)
    bundle = canon.load_json(os.path.join(OUT, "review-input-bundle.json"))
    bound = {
        "ratified_brief": bundle["bindings"]["brief"],
        "review_input_bundle": _bound(os.path.join(OUT, "review-input-bundle.json")),
        "review_universe": _bound(os.path.join(OUT, "review-universe.json")),
        "natural_universe_sealed": _bound(os.path.join(OUT, "sealed", "natural-universe.json")),
        "reviewer_a_identity": _bound(os.path.join(a_dir, "reviewer-identity.json")),
        "reviewer_b_identity": _bound(os.path.join(b_dir, "reviewer-identity.json"))
            if os.path.isfile(os.path.join(b_dir, "reviewer-identity.json")) else "MISSING",
        "reviewer_a_outputs": report["appendices"]["reviewer_a_outputs"],
        "reviewer_b_outputs": report["appendices"]["reviewer_b_outputs"],
        "partition": report["appendices"]["partition"],
        "exclusions_appendix": report["appendices"]["exclusions"],
        "release_report": _bound(os.path.join(OUT, "gate", "release-report.json")),
        "release_candidate": report["appendices"]["release_candidate"],
        "control_grading": _bound(os.path.join(OUT, "gate", "control-grading.json"))
            if os.path.isfile(os.path.join(OUT, "gate", "control-grading.json"))
            else "PENDING ORACLE REVEAL",
    }
    manifest_sha = gate.release_manifest(OUT, bound)
    s = report["decision_summary"]
    print("natural:", s["natural_release_universe"], "accepted:",
          s["unanimously_accepted_natural"], "rate:", s["acceptance_rate_natural"],
          "units:", s["units_with_at_least_one_accepted_natural_claim"])
    print("gates:", {k: (v["pass"] if isinstance(v, dict) else v)
                     for k, v in report["gates"].items()})
    print("reconciliation:", report["partition_counts"]["reconciliation"])
    print("RELEASE_MANIFEST_SHA256:", manifest_sha,
          "(provisional until control grading is bound)")


if __name__ == "__main__":
    main()
