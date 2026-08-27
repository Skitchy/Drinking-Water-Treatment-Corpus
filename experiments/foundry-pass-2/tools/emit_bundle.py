"""Emit the Pass 2 review-input bundle from the fixed Pass 1 outputs and the
ratified evaluator bundle. Run from experiments/foundry-pass-2:

    python3 tools/emit_bundle.py [--controls PATH]

--controls points at the control-record bundle to mix in. Default: Ari's
public v0.1 bundle (identities public; superseded per Ari's 2026-08-27
ruling). The replacement controls live OUTSIDE public git; the mixed review
universe and shards they produce (out/review-universe.json, out/shards/,
out/sealed/) are git-ignored until both reviewer outputs are fixed. Only
out/review-input-bundle.json (digests and commitments) is committed pre-run.

This is the only place that knows where the adapter and the evaluator
artifacts live; the engine receives objects and digests.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS2 = os.path.dirname(HERE)
sys.path.insert(0, PASS2)

from engine import canon, universe  # noqa: E402
from adapters.ecfr_pass1.adapter import EcfrPass1Adapter  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(PASS2, "..", ".."))
ARI = os.path.join(PASS2, "evaluator", "ari")
OUT = os.path.join(PASS2, "out")

RATIFIED = {
    "maintainer_ratification_comment": "discussioncomment-18176893",
    "brief_path": "proposals/foundry-pass-2-experiment-brief-v0.3.md",
    "brief_commit": "809c663",
    "brief_sha256":
        "6e83818e106f494bb2101472ef7fa1e65c249a3ad78b35cb02075205bfb0132b",
    "evaluator_manifest_commit": "e7e3945",
    "evaluator_manifest_sha256":
        "2c6739f39dbc5a121510be088ef8ffb129ef2a84b740e6ded395343c0baf6a59",
    "sealed_oracle_sha256":
        "f3364e089e5b5b46455db723bacc9ffd3dc282d76aead839555b112c2c93d1f0",
    "sealed_oracle_byte_length": 16548,
}


def _bound(path):
    return {"path": os.path.relpath(path, REPO_ROOT),
            "sha256": canon.file_sha256(path),
            "byte_length": os.path.getsize(path)}


def main():
    controls_path = os.path.join(ARI, "control-records-v0.1.json")
    if "--controls" in sys.argv:
        controls_path = os.path.abspath(sys.argv[sys.argv.index("--controls") + 1])
    # Bind the ratified artifacts by recomputing, not trusting, their digests.
    brief = _bound(os.path.join(REPO_ROOT, RATIFIED["brief_path"]))
    if brief["sha256"] != RATIFIED["brief_sha256"]:
        raise SystemExit("brief digest does not match the ratification")
    manifest = _bound(os.path.join(ARI, "ari-evaluator-public-manifest-v0.1.json"))
    if manifest["sha256"] != RATIFIED["evaluator_manifest_sha256"]:
        raise SystemExit("evaluator manifest digest does not match the ratification")
    bindings = {
        "ratification": RATIFIED,
        "brief": brief,
        "evaluator_manifest": manifest,
        "reviewer_contract": _bound(os.path.join(ARI, "isolated-reviewer-contract-v0.1.json")),
        "reviewer_system_prompt": _bound(os.path.join(ARI, "reviewer-system-prompt-v0.1.md")),
        "reviewer_task_template": _bound(os.path.join(ARI, "reviewer-task-template-v0.1.md")),
        "reviewer_output_schema": _bound(os.path.join(ARI, "reviewer-output-v0.1.schema.json")),
        "control_records_bundle": {"sha256": canon.file_sha256(controls_path),
                                   "byte_length": os.path.getsize(controls_path),
                                   "location": "private until outputs are fixed"
                                   if not controls_path.startswith(REPO_ROOT)
                                   else os.path.relpath(controls_path, REPO_ROOT)},
        "mixed_control_commitment": _bound(os.path.join(ARI, "mixed-control-commitment-v0.1.json")),
    }
    controls = canon.load_json(controls_path)["records"]
    bundle = universe.emit_bundle(OUT, EcfrPass1Adapter(), controls, bindings)
    bundle_sha = canon.file_sha256(os.path.join(OUT, "review-input-bundle.json"))
    print("review universe:", bundle["review_universe"]["record_count"])
    print("natural (sealed):", bundle["natural_universe_sealed"]["record_count"])
    print("shards:", bundle["shard_manifest"]["shard_count"])
    print("units without records:", bundle["unit_ids_without_records"])
    print("REVIEW_INPUT_BUNDLE_SHA256:", bundle_sha)


if __name__ == "__main__":
    main()
