"""Foundry Pass 1 orchestrator, stages 0-2.

Emits, all under experiments/foundry-pass-1/ (brief section 9):
  out/capture-verification.json   per-member stage-0 records (class 1)
  out/canonical/<section>.json    canonical representation, dual anchors (class 1)
  out/canonical-index.json        section -> canonical payload digest (class 1)
  out/run-envelope.json           time/actor/environment (class 2, excluded
                                  from replay comparison)
  out/failure-log.jsonl           append-only, chained heads

Usage: python3 run_compile.py [--envelope-note TEXT]
Exit code 0 only if stage 0 verified every member and stages 1-2 produced
canonical output for every verified capture.
"""

import json
import os
import sys

import foundry_lib
from canonicalize import canonicalize_capture

COMPILER_DIR = os.path.dirname(os.path.abspath(__file__))
EXPERIMENT_DIR = os.path.dirname(COMPILER_DIR)
REPO_ROOT = os.path.dirname(os.path.dirname(EXPERIMENT_DIR))
OUT_DIR = os.path.join(EXPERIMENT_DIR, "out")
INPUT_MANIFEST = os.path.join(EXPERIMENT_DIR, "evaluator", "input-manifest.json")


def main():
    with open(INPUT_MANIFEST, "rb") as f:
        manifest_bytes = f.read()
    manifest = json.loads(manifest_bytes)

    # Stage 0: closed-input verification, fail closed per member.
    records, failures = foundry_lib.verify_input_bundle(REPO_ROOT, manifest)
    stage0 = {
        "input_manifest_sha256": foundry_lib.file_sha256(INPUT_MANIFEST),
        "input_bundle_sha256": manifest["bundle_identity"]["bundle_sha256"],
        "verified": records,
        "failed_closed": failures,
    }
    foundry_lib.write_canonical(
        os.path.join(OUT_DIR, "capture-verification.json"), stage0)

    log_path = os.path.join(OUT_DIR, "failure-log.jsonl")
    head = None
    for failure in failures:
        head = foundry_lib.chained_append(log_path, failure, head)

    verified_paths = {r["member_path"] for r in records}
    captures = [m for m in manifest["members"]
                if m["role"] == "authoritative-capture"
                and m["path"] in verified_paths]

    # Stages 1-2: canonicalization with dual anchors, verified captures only.
    index = {}
    for member in sorted(captures, key=lambda m: m["path"]):
        for result in canonicalize_capture(REPO_ROOT, member["path"]):
            section = result["section"]
            name = f"section-{section['section_number']}"
            out_path = os.path.join(OUT_DIR, "canonical", f"{name}.json")
            digest = foundry_lib.write_canonical(out_path, section)
            assert digest == result["canonical_sha256"]
            index[section["section_number"]] = {
                "path": f"experiments/foundry-pass-1/out/canonical/{name}.json",
                "canonical_sha256": digest,
                "capture_path": member["path"],
                "capture_sha256": member["sha256"],
                "anchors_derived": sum(
                    1 for a in section["logical_anchors"]
                    if a["status"] == "derived"),
                "anchor_review_items": sum(
                    1 for a in section["logical_anchors"]
                    if a["status"] == "review-item"),
            }
    foundry_lib.write_canonical(
        os.path.join(OUT_DIR, "canonical-index.json"), index)

    # Class-2 envelope: the only place ambient state is recorded.
    import datetime
    import platform
    envelope = {
        "class": "run-event-envelope",
        "excluded_from_replay_comparison": True,
        "recorded_at_utc": datetime.datetime.now(
            datetime.timezone.utc).isoformat(),
        "actor": "cc-foundry-compiler",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "note": " ".join(sys.argv[2:]) if len(sys.argv) > 2
                and sys.argv[1] == "--envelope-note" else "",
    }
    with open(os.path.join(OUT_DIR, "run-envelope.json"), "w",
              encoding="utf-8") as f:
        json.dump(envelope, f, indent=2, sort_keys=True)
        f.write("\n")

    summary = {
        "members_verified": len(records),
        "members_failed_closed": len(failures),
        "sections_canonicalized": len(index),
        "anchors_derived": sum(v["anchors_derived"] for v in index.values()),
        "anchor_review_items": sum(
            v["anchor_review_items"] for v in index.values()),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if not failures and len(index) > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
