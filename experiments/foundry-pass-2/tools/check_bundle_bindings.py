"""Public re-verification of the committed review-input bundle, without the
private controls. Run from experiments/foundry-pass-2 (CI runs it):

    python3 tools/check_bundle_bindings.py

Checks that every public artifact the committed out/review-input-bundle.json
binds still recomputes to the bound digest and length (brief, evaluator
manifest, contract, prompts, schema, commitment, verifier, and the adapter's
fixed Pass 1 inputs), and that the private control-bundle and sealed-oracle
commitments in the bundle equal the ones in mixed-control-commitment-v0.2.json.
It cannot regenerate the bundle (that needs the private controls); the
byte-identical regeneration replay is recorded in the run record instead.
Exit 1 on any mismatch.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS2 = os.path.dirname(HERE)
sys.path.insert(0, PASS2)
sys.path.insert(0, HERE)

from engine import canon  # noqa: E402
from adapters.ecfr_pass1.adapter import EcfrPass1Adapter  # noqa: E402
import emit_bundle  # noqa: E402

BUNDLE = os.path.join(PASS2, "out", "review-input-bundle.json")


def check(bundle_path=BUNDLE):
    bundle = canon.load_json(bundle_path)
    live = emit_bundle.public_bindings()      # recomputed from the tree
    bound = bundle["bindings"]
    problems = []
    for key, value in live.items():
        if bound.get(key) != value:
            problems.append(f"binding drift: {key}")
    if bound.get("proposed_packet") != emit_bundle.PROPOSED:
        problems.append("proposed packet block drift")
    if bundle["adapter_fixed_inputs"] != EcfrPass1Adapter().fixed_input_identity():
        problems.append("adapter fixed inputs drift")
    if not problems:
        return {"status": "PASS", "review_input_bundle_sha256":
                canon.file_sha256(bundle_path)}
    return {"status": "FAIL", "problems": problems}


def main():
    result = check()
    print(result)
    if result["status"] != "PASS":
        sys.exit(1)


if __name__ == "__main__":
    main()
