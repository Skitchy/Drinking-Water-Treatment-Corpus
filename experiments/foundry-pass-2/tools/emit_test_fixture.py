"""Build a PUBLIC test fixture universe so the harness and gate tests can run
without the private controls (CI cannot hold them). From experiments/foundry-pass-2:

    python3 tools/emit_test_fixture.py        # writes out-fixture/ (git-ignored)
    FOUNDRY_PASS2_OUT=out-fixture python3 -m unittest discover -s tests -t .

The fixture mixes the BURNED public v0.1 controls (identities public by
design; never used for the experiment) into the fixed Pass 1 natural universe
and writes everything into out-fixture/, never out/. Its bundle is labeled a
fixture and binds nothing ratified or proposed, so it can never be mistaken
for the run bundle: out/review-input-bundle.json is untouched by this tool.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS2 = os.path.dirname(HERE)
sys.path.insert(0, PASS2)

from engine import canon, universe  # noqa: E402
from adapters.ecfr_pass1.adapter import EcfrPass1Adapter  # noqa: E402

ARI = os.path.join(PASS2, "evaluator", "ari")
FIXTURE_OUT = os.path.join(PASS2, "out-fixture")
BURNED_CONTROLS = os.path.join(ARI, "control-records-v0.1.json")


def main():
    if os.path.abspath(FIXTURE_OUT) == os.path.join(PASS2, "out"):
        raise SystemExit("fixture must never write into out/")
    bindings = {
        "FIXTURE": "test fixture built from the burned public v0.1 controls; "
                   "not the experiment bundle; binds nothing ratified",
        "control_records_bundle": {"sha256": canon.file_sha256(BURNED_CONTROLS),
                                   "byte_length": os.path.getsize(BURNED_CONTROLS),
                                   "location": os.path.relpath(BURNED_CONTROLS, PASS2)},
        # the harness/gate tests read these two keys from the bundle
        "reviewer_contract": {"path": "evaluator/ari/isolated-reviewer-contract-v0.2.json",
                              "sha256": canon.file_sha256(
                                  os.path.join(ARI, "isolated-reviewer-contract-v0.2.json"))},
        "brief": {"path": "FIXTURE", "sha256": "0" * 64},
    }
    controls = canon.load_json(BURNED_CONTROLS)["records"]
    bundle = universe.emit_bundle(FIXTURE_OUT, EcfrPass1Adapter(), controls, bindings)
    print("fixture review universe:", bundle["review_universe"]["record_count"])
    print("fixture shards:", bundle["shard_manifest"]["shard_count"])
    print("fixture dir:", os.path.relpath(FIXTURE_OUT, PASS2))


if __name__ == "__main__":
    main()
