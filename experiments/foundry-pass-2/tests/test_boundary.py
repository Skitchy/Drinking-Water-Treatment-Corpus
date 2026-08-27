"""Boundary tests. Run from experiments/foundry-pass-2:
    python3 -m unittest tests.test_boundary -v
"""

import os
import re
import unittest

from engine import canon, records, contract
from adapters.ecfr_pass1.adapter import EcfrPass1Adapter

HERE = os.path.dirname(os.path.abspath(__file__))
PASS2 = os.path.dirname(HERE)
ENGINE = os.path.join(PASS2, "engine")
ARI = os.path.join(PASS2, "evaluator", "ari")

# Tokens that would mean eCFR leaked into the engine. The engine may not
# know what a CFR section, a DIV8, a Pass 1 tree, or a subpart is.
FORBIDDEN_IN_ENGINE = re.compile(
    r"ecfr|cfr|DIV8|141\.|subpart|foundry-pass-1|foundry_pass_1|pass1|"
    r"xml|eCFR", re.IGNORECASE)


class EngineIsSubjectAgnostic(unittest.TestCase):
    def test_no_source_specific_tokens_in_engine(self):
        hits = []
        for name in sorted(os.listdir(ENGINE)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(ENGINE, name), encoding="utf-8") as f:
                for lineno, line in enumerate(f, 1):
                    if FORBIDDEN_IN_ENGINE.search(line):
                        hits.append(f"{name}:{lineno}: {line.rstrip()}")
        self.assertEqual(hits, [], "engine names a source type:\n" +
                         "\n".join(hits))

    def test_engine_imports_no_adapter(self):
        for name in os.listdir(ENGINE):
            if name.endswith(".py"):
                with open(os.path.join(ENGINE, name), encoding="utf-8") as f:
                    imports = [l for l in f if l.startswith(("import ", "from "))]
                self.assertFalse(any("adapters" in l for l in imports), name)


class EngineReproducesAriCanonicalization(unittest.TestCase):
    """Rebuild each of Ari's 21 control records from its payload, evidence,
    ambiguities, and section through engine.records and require identical
    digests and artifact ids. This is the cross-lineage proof that the
    engine's canonicalization is the contract's, not an approximation."""

    def test_control_records_round_trip(self):
        bundle = canon.load_json(
            os.path.join(ARI, "control-records-v0.1.json"))
        self.assertEqual(len(bundle["records"]), 21)
        for item in bundle["records"]:
            candidate = {
                "unit_id": item["source_section"],
                "candidate_id": "control",
                "claim_payload": item["claim_payload"],
                "evidence": item["evidence"],
            }
            rebuilt = records.build_record(
                candidate, item["declared_section_ambiguities"])
            for key in ("record_sha256", "artifact_id", "claim_payload_sha256",
                        "normalized_support_anchor_set_sha256",
                        "normalized_support_anchor_set"):
                self.assertEqual(rebuilt[key], item[key],
                                 f"{key} differs for {item['artifact_id']}")

    def test_control_records_verify_against_adapter_units(self):
        bundle = canon.load_json(
            os.path.join(ARI, "control-records-v0.1.json"))
        adapter = EcfrPass1Adapter()
        for item in bundle["records"]:
            unit = adapter.unit(item["source_section"])
            result = records.verify_record(item, unit)
            self.assertEqual(result["verdict"], "verified",
                             f"{item['artifact_id']}: {result['problems']}")


class AdapterHonorsContract(unittest.TestCase):
    def setUp(self):
        self.adapter = EcfrPass1Adapter()

    def test_units_validate(self):
        ids = self.adapter.unit_ids()
        self.assertEqual(len(ids), 38)
        for unit_id in ids:
            contract.validate_source_unit(self.adapter.unit(unit_id))

    def test_all_natural_candidates_build_and_verify(self):
        total = 0
        for unit_id in self.adapter.unit_ids():
            unit = self.adapter.unit(unit_id)
            ambiguities = self.adapter.ambiguities(unit_id)
            for candidate in self.adapter.candidates(unit_id):
                contract.validate_candidate(candidate)
                record = records.build_record(candidate, ambiguities)
                result = records.verify_record(record, unit)
                self.assertEqual(result["verdict"], "verified",
                                 f"{unit_id}/{candidate['candidate_id']}: "
                                 f"{result['problems']}")
                total += 1
        self.assertEqual(total, 387)

    def test_control_ambiguities_match_adapter_ambiguities(self):
        """Ari built controls from the same Pass 1 ambiguities; if the
        adapter reads them differently, natural and control records in one
        shard would be distinguishable by that field alone."""
        bundle = canon.load_json(
            os.path.join(ARI, "control-records-v0.1.json"))
        for item in bundle["records"]:
            self.assertEqual(
                item["declared_section_ambiguities"],
                self.adapter.ambiguities(item["source_section"]),
                item["artifact_id"])

    def test_natural_and_control_artifact_ids_disjoint(self):
        bundle = canon.load_json(
            os.path.join(ARI, "control-records-v0.1.json"))
        control_ids = {r["artifact_id"] for r in bundle["records"]}
        natural_ids = set()
        for unit_id in self.adapter.unit_ids():
            ambiguities = self.adapter.ambiguities(unit_id)
            for candidate in self.adapter.candidates(unit_id):
                natural_ids.add(records.build_record(
                    candidate, ambiguities)["artifact_id"])
        self.assertEqual(len(natural_ids), 387, "natural ids collide")
        self.assertEqual(natural_ids & control_ids, set())


if __name__ == "__main__":
    unittest.main()
