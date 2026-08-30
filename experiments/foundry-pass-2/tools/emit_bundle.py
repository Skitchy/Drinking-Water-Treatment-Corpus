"""Emit the Pass 2 review-input bundle from the fixed Pass 1 outputs and Ari's
v0.3 evaluator packet. Run from experiments/foundry-pass-2:

    python3 tools/emit_bundle.py --controls /private/path/control-records-v0.3.json

--controls is REQUIRED. There is no default: the v0.1 control bundle in
evaluator/ari/ is public and its identities are burned (Ari's 2026-08-27
ruling, discussioncomment-18177749). The replacement controls live OUTSIDE
public git; the emitter refuses any controls file whose bytes do not match
the digest and length committed in mixed-control-commitment-v0.3.json, and
refuses a path inside the repository.

The mixed review universe and shards (out/review-universe.json, out/shards/,
out/sealed/) are git-ignored until both reviewer outputs are fixed. Only
out/review-input-bundle.json (digests and commitments) is committed pre-run.
The bundle is content-addressed: the maintainer's ratification names its
digest; the bundle does not name the ratification. Public re-verification of
the committed bundle without the private controls is tools/check_bundle_bindings.py.

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

# Ari's v0.3 packet (discussioncomment-18206443), pending fresh ratification.
PROPOSED = {
    "status": "proposed-for-content-bound-maintainer-ratification",
    "supersedes_ratification": "discussioncomment-18176893 (brief v0.3; "
                               "superseded before any reviewer ran)",
    "evaluator_packet_comment": "discussioncomment-18206443",
    "supersedes_packet": "v0.2 (discussioncomment-18187089; ratified 18187784; "
                         "superseded by maintainer ruling 18206234)",
    "brief_path": "proposals/foundry-pass-2-experiment-brief-v0.4-DRAFT.md",
    "brief_commit": "8a45e78",
    "brief_sha256":
        "31468a1773d8928634e508c5508257c982131e95cbf64553478158a204b5d1c7",
    "evaluator_manifest_path":
        "experiments/foundry-pass-2/evaluator/ari/ari-evaluator-public-manifest-v0.3.json",
    "evaluator_manifest_sha256":
        "6afb3d92e5fe4ed5c2218ed70ada20a93f2bea4bacf62df372c103dec00f4609",
    "sealed_oracle_sha256":
        "eb32264a19b34b7dbaac1875bce4bdbcc0969a9f11a27a89b98d7feec25c1d8d",
    "sealed_oracle_byte_length": 27615,
}

PUBLIC_MEMBERS = {
    "evaluator_manifest": "ari-evaluator-public-manifest-v0.3.json",
    "reviewer_contract": "isolated-reviewer-contract-v0.3.json",
    "mixed_control_commitment": "mixed-control-commitment-v0.3.json",
    "public_bundle_verifier": "verify-ari-evaluator-bundle-v0.1.2.py",
    "reviewer_system_prompt": "reviewer-system-prompt-v0.1.md",
    "reviewer_task_template": "reviewer-task-template-v0.1.md",
    "reviewer_output_schema": "reviewer-output-v0.1.schema.json",
}


def _bound(path):
    return {"path": os.path.relpath(path, REPO_ROOT),
            "sha256": canon.file_sha256(path),
            "byte_length": os.path.getsize(path)}


def public_bindings():
    """Recompute, never trust, the digests of every bound public artifact.
    Raises SystemExit on any mismatch with the proposed packet."""
    brief = _bound(os.path.join(REPO_ROOT, PROPOSED["brief_path"]))
    if brief["sha256"] != PROPOSED["brief_sha256"]:
        raise SystemExit("brief digest does not match the proposed packet")
    bound = {key: _bound(os.path.join(ARI, name))
             for key, name in PUBLIC_MEMBERS.items()}
    if bound["evaluator_manifest"]["sha256"] != PROPOSED["evaluator_manifest_sha256"]:
        raise SystemExit("evaluator manifest digest does not match the proposed packet")
    commitment = canon.load_json(os.path.join(ARI, PUBLIC_MEMBERS["mixed_control_commitment"]))
    cb = commitment["bindings"]
    if cb["brief_sha256"] != brief["sha256"]:
        raise SystemExit("commitment binds a different brief")
    if cb["reviewer_contract_sha256"] != bound["reviewer_contract"]["sha256"]:
        raise SystemExit("commitment binds a different reviewer contract")
    if cb["public_bundle_verifier_sha256"] != bound["public_bundle_verifier"]["sha256"]:
        raise SystemExit("commitment binds a different public verifier")
    oracle = commitment["sealed_oracle"]
    if (oracle["sha256"], oracle["byte_length"]) != (
            PROPOSED["sealed_oracle_sha256"], PROPOSED["sealed_oracle_byte_length"]):
        raise SystemExit("commitment binds a different sealed oracle")
    bindings = {"proposed_packet": PROPOSED, "brief": brief}
    bindings.update(bound)
    bindings["control_records_bundle"] = {
        "sha256": cb["control_records_bundle"]["sha256"],
        "byte_length": cb["control_records_bundle"]["byte_length"],
        "location": "private until both reviewer outputs are fixed",
    }
    bindings["sealed_oracle"] = {
        "sha256": oracle["sha256"],
        "byte_length": oracle["byte_length"],
        "location": "evaluator and maintainer only until reveal",
    }
    return bindings


def resolve_controls(argv):
    if "--controls" not in argv:
        raise SystemExit("--controls PATH is required: the public v0.1 controls "
                         "are burned and there is no default")
    path = os.path.abspath(argv[argv.index("--controls") + 1])
    if path.startswith(REPO_ROOT + os.sep):
        raise SystemExit("controls must live outside the repository until "
                         "both reviewer outputs are fixed")
    return path


def main(argv=None):
    argv = sys.argv if argv is None else argv
    controls_path = resolve_controls(argv)
    bindings = public_bindings()
    expected = bindings["control_records_bundle"]
    actual = {"sha256": canon.file_sha256(controls_path),
              "byte_length": os.path.getsize(controls_path)}
    if (actual["sha256"], actual["byte_length"]) != (
            expected["sha256"], expected["byte_length"]):
        raise SystemExit("controls file does not match the committed "
                         "control-bundle digest and length")
    controls = canon.load_json(controls_path)["records"]
    bundle = universe.emit_bundle(OUT, EcfrPass1Adapter(), controls, bindings)
    bundle_sha = canon.file_sha256(os.path.join(OUT, "review-input-bundle.json"))
    print("review universe:", bundle["review_universe"]["record_count"])
    print("natural (sealed):", bundle["natural_universe_sealed"]["record_count"])
    print("shards:", bundle["shard_manifest"]["shard_count"])
    print("units without records:", bundle["unit_ids_without_records"])
    print("REVIEW_INPUT_BUNDLE_SHA256:", bundle_sha)
    return bundle_sha


if __name__ == "__main__":
    main()
