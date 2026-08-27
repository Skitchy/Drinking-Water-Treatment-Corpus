"""Adapter #1: eCFR, as fixed by the clean Foundry Pass 1 outputs (git
4574c8f). Everything eCFR-shaped lives on this side of the boundary: the
Pass 1 out/ layout, the section-number unit ids, the DIV8 selector scheme,
the Pass 1 claim shape and its mapping onto the contract payload.

Scope guard (brief 7a, Ari): this adapter CONSUMES the fixed Pass 1
extraction; it does not re-extract, re-canonicalize, or refactor Pass 1.
"""

import os

from engine import canon
from engine.contract import SourceAdapter, ADAPTER_CONTRACT_VERSION

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
PASS1_OUT = os.path.join(REPO_ROOT, "experiments", "foundry-pass-1", "out")
FIXED_PASS1_COMMIT = "4574c8f"

# Pass 1 emitted eight claim fields. The contract payload has nine; the three
# Pass 1 never emitted are filled empty here, exactly as Ari's control
# records fill them, so natural and control payloads share one shape.
PASS1_CLAIM_FIELDS = ("kind", "subject", "relation", "value", "unit",
                      "conditions")


class EcfrPass1Adapter(SourceAdapter):
    source_kind = "ecfr-xml-capture"

    def __init__(self, out_dir=PASS1_OUT):
        self.out_dir = out_dir
        self.index = canon.load_json(
            os.path.join(out_dir, "canonical-index.json"))
        self._verified = {}
        self._canonical = {}

    # ---- fixed-input access ------------------------------------------------

    def _canonical_section(self, unit_id):
        if unit_id not in self._canonical:
            self._canonical[unit_id] = canon.load_json(os.path.join(
                self.out_dir, "canonical", f"section-{unit_id}.json"))
        return self._canonical[unit_id]

    def _verified_section(self, unit_id):
        if unit_id not in self._verified:
            self._verified[unit_id] = canon.load_json(os.path.join(
                self.out_dir, "verified", f"verified-{unit_id}.json"))
        return self._verified[unit_id]

    # ---- SourceAdapter interface ------------------------------------------

    def unit_ids(self):
        return sorted(self.index)

    def unit(self, unit_id):
        entry = self.index[unit_id]
        section = self._canonical_section(unit_id)
        return {
            "unit_id": unit_id,
            "source_kind": self.source_kind,
            "capture_path": entry["capture_path"],
            "capture_sha256": entry["capture_sha256"],
            "canonical_sha256": entry["canonical_sha256"],
            "representation": section["tree"],
            "anchor_rules": {
                "selector_scheme": "pass1-xml-path-v1 (TAG[i]; DIV8[N=...])",
                "text_profile": "pass1-normalize-text-v1 (NFC, whitespace "
                                "runs collapsed, stripped)",
                "custody": [
                    {"kind": "capture-bytes", "digest_field": "capture_sha256"},
                ],
            },
        }

    def candidates(self, unit_id):
        verified = self._verified_section(unit_id)
        quotes = {q["id"]: q for q in verified["verified_quotes"]}
        out = []
        for claim in verified["verified_claims"]:
            payload = {k: claim[k] for k in PASS1_CLAIM_FIELDS}
            payload["applicability"] = []
            payload["effective_time"] = None
            payload["dependencies"] = []
            evidence = []
            for quote_id in claim["supporting_quotes"]:
                quote = quotes[quote_id]
                binding = quote["binding"]
                evidence.append({
                    "exact_text": quote["exact_text"],
                    "support_anchor": {
                        "capture_sha256": binding["capture_sha256"],
                        "selector": binding["selector"],
                        "char_start": binding["char_start"],
                        "char_end": binding["char_end"],
                        "span_sha256": binding["span_sha256"],
                        "logical_anchor": quote["logical_anchor"],
                    },
                })
            out.append({
                "unit_id": unit_id,
                "candidate_id": claim["candidate_claim_id"],
                "claim_payload": payload,
                "evidence": evidence,
            })
        return out

    def ambiguities(self, unit_id):
        return list(self._verified_section(unit_id)["ambiguities_declared"])

    def fixed_input_identity(self):
        members = []
        for unit_id in self.unit_ids():
            for sub in ("canonical", "verified"):
                name = ("section-" if sub == "canonical" else "verified-") \
                    + unit_id + ".json"
                path = os.path.join(self.out_dir, sub, name)
                members.append({
                    "path": os.path.relpath(path, REPO_ROOT),
                    "sha256": canon.file_sha256(path),
                    "byte_length": os.path.getsize(path),
                })
        index_path = os.path.join(self.out_dir, "canonical-index.json")
        members.append({
            "path": os.path.relpath(index_path, REPO_ROOT),
            "sha256": canon.file_sha256(index_path),
            "byte_length": os.path.getsize(index_path),
        })
        return {
            "adapter": "ecfr_pass1",
            "contract_version": ADAPTER_CONTRACT_VERSION,
            "fixed_pass_1_output_commit": FIXED_PASS1_COMMIT,
            "members": sorted(members, key=lambda m: m["path"]),
        }
