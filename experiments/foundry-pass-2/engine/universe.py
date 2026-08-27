"""Review universe, natural universe, shards, and the review-input bundle
manifest (brief 4a, 3a; Ari's contract "input_contract").

Two universes, defined separately:
  natural release universe = every release-eligible record built from the
                             adapter's candidates, by artifact id;
  review universe          = natural + sealed controls, disjoint union,
                             interleaved indistinguishably.
The natural listing is written under seal (out/sealed/) and only its digest
enters reviewer-visible material. Shards are one per unit, byte-identical
for both reviewers, records ordered by artifact id (a digest prefix, so the
order carries no origin signal).

Everything written here is class-1: same inputs produce the same bytes.
"""

import os

from . import canon
from .contract import validate_source_unit
from .records import build_record, verify_record

UNIVERSE_VERSION = "foundry-review-universe/experimental-v0.1"
SHARD_VERSION = "foundry-review-shard/experimental-v0.1"
BUNDLE_VERSION = "foundry-review-input-bundle/experimental-v0.1"

# Keys that must never appear anywhere in reviewer-visible bytes. The first
# group is the control-metadata set from the evaluator's own verifier; the
# rest are engine-side origin markers.
FORBIDDEN_VISIBLE_KEYS = frozenset({
    "base_natural_record_sha256", "certification", "error_class",
    "expected_acceptability", "mutation_description", "source_claim", "source_quote",
    "truth_label", "control_class", "expected_verdict", "origin",
    "is_control", "candidate_id",
})


class UniverseError(Exception):
    """Fail closed: nothing is emitted when the universe cannot be built
    exactly."""


def _walk_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def build_universe(adapter, control_records):
    """Returns (units, natural, controls) where units maps unit_id ->
    SourceUnit, natural maps artifact_id -> record, controls likewise.
    Every record, natural or control, is verified against its unit before
    it can enter; a control whose unit the adapter does not have is a
    hard stop (a control must be indistinguishable, so it must bind to a
    real unit)."""
    units = {}
    natural = {}
    controls = {}
    for unit_id in adapter.unit_ids():
        unit = adapter.unit(unit_id)
        validate_source_unit(unit)
        units[unit_id] = unit
        ambiguities = adapter.ambiguities(unit_id)
        for candidate in adapter.candidates(unit_id):
            record = build_record(candidate, ambiguities)
            check = verify_record(record, unit)
            if check["verdict"] != "verified":
                raise UniverseError(
                    f"natural record failed verification: {check}")
            if record["artifact_id"] in natural:
                raise UniverseError(
                    f"duplicate natural artifact id {record['artifact_id']}")
            natural[record["artifact_id"]] = record
    for record in control_records:
        unit = units.get(record["source_section"])
        if unit is None:
            raise UniverseError(
                f"control {record['artifact_id']} binds to unknown unit "
                f"{record['source_section']}")
        check = verify_record(record, unit)
        if check["verdict"] != "verified":
            raise UniverseError(
                f"control record failed verification: {check}")
        if record["artifact_id"] in natural or record["artifact_id"] in controls:
            raise UniverseError(
                f"control artifact id collides: {record['artifact_id']}")
        controls[record["artifact_id"]] = record
    return units, natural, controls


def _listing_entry(record):
    return {
        "artifact_id": record["artifact_id"],
        "record_sha256": record["record_sha256"],
        "claim_payload_sha256": record["claim_payload_sha256"],
        "normalized_support_anchor_set_sha256":
            record["normalized_support_anchor_set_sha256"],
        "unit_id": record["source_section"],
    }


def _shard_record(record):
    """Reviewer-visible record: exactly the contract's required fields."""
    return {k: record[k] for k in (
        "artifact_id", "record_sha256", "claim_payload_sha256",
        "normalized_support_anchor_set_sha256", "source_section",
        "claim_payload", "normalized_support_anchor_set", "evidence",
        "declared_section_ambiguities")}


def _shard_source_context(unit):
    return {
        "unit_id": unit["unit_id"],
        "capture_path": unit["capture_path"],
        "capture_sha256": unit["capture_sha256"],
        "canonical_sha256": unit["canonical_sha256"],
        "anchor_rules": unit["anchor_rules"],
        "representation": unit["representation"],
    }


def emit_bundle(out_dir, adapter, control_records, bindings):
    """Write the review-input bundle. `bindings` carries the digests of the
    ratified artifacts the bundle must bind (brief, contract, prompts,
    schema, control bundle); the engine records them and never reads the
    files behind them.

    Returns the bundle manifest dict (its file digest is the
    REVIEW_INPUT_BUNDLE_SHA256 every reviewer session is handed)."""
    units, natural, controls = build_universe(adapter, control_records)
    review = dict(natural)
    review.update(controls)

    # --- universes -------------------------------------------------------
    by_unit = {}
    for record in review.values():
        by_unit.setdefault(record["source_section"], []).append(record)
    review_listing = {
        "artifact_version": UNIVERSE_VERSION,
        "universe": "review",
        "record_count": len(review),
        "records": [_listing_entry(review[k]) for k in sorted(review)],
        "unit_counts": {u: len(v) for u, v in sorted(by_unit.items())},
    }
    review_digest = canon.write_canonical(
        os.path.join(out_dir, "review-universe.json"), review_listing)
    natural_listing = {
        "artifact_version": UNIVERSE_VERSION,
        "universe": "natural-release",
        "record_count": len(natural),
        "records": [_listing_entry(natural[k]) for k in sorted(natural)],
        "control_count": len(controls),
        "control_artifact_ids": sorted(controls),
    }
    natural_digest = canon.write_canonical(
        os.path.join(out_dir, "sealed", "natural-universe.json"),
        natural_listing)

    # --- shards ----------------------------------------------------------
    shard_members = []
    for unit_id in sorted(units):
        records = sorted(by_unit.get(unit_id, []),
                         key=lambda r: r["artifact_id"])
        if not records:
            continue  # a unit with nothing to review yields no shard
        shard = {
            "artifact_version": SHARD_VERSION,
            "shard_id": f"shard-{unit_id}",
            "unit_id": unit_id,
            "record_count": len(records),
            "records": [_shard_record(r) for r in records],
            "source_context": _shard_source_context(units[unit_id]),
        }
        leaked = set(_walk_keys(shard)) & FORBIDDEN_VISIBLE_KEYS
        if leaked:
            raise UniverseError(
                f"forbidden key in reviewer-visible shard {unit_id}: "
                f"{sorted(leaked)}")
        rel = os.path.join("shards", f"{shard['shard_id']}.json")
        digest = canon.write_canonical(os.path.join(out_dir, rel), shard)
        shard_members.append({
            "shard_id": shard["shard_id"],
            "unit_id": unit_id,
            "path": rel,
            "sha256": digest,
            "byte_length": os.path.getsize(os.path.join(out_dir, rel)),
            "record_count": len(records),
            "artifact_ids": [r["artifact_id"] for r in records],
        })
    shard_manifest = {
        "artifact_version": BUNDLE_VERSION + "/shard-manifest",
        "shard_count": len(shard_members),
        "record_count": sum(m["record_count"] for m in shard_members),
        "shards": shard_members,
    }
    shard_manifest_digest = canon.write_canonical(
        os.path.join(out_dir, "shard-manifest.json"), shard_manifest)
    if shard_manifest["record_count"] != len(review):
        raise UniverseError("shard records do not sum to the review universe")

    # --- bundle manifest -------------------------------------------------
    bundle = {
        "artifact_version": BUNDLE_VERSION,
        "bindings": dict(bindings),
        "adapter_fixed_inputs": adapter.fixed_input_identity(),
        "review_universe": {"path": "review-universe.json",
                            "sha256": review_digest,
                            "record_count": len(review)},
        "natural_universe_sealed": {"sha256": natural_digest,
                                    "record_count": len(natural),
                                    "listing": "under seal until grading"},
        "shard_manifest": {"path": "shard-manifest.json",
                           "sha256": shard_manifest_digest,
                           "shard_count": len(shard_members)},
        "unit_ids_without_records": sorted(
            u for u in units if not by_unit.get(u)),
    }
    canon.write_canonical(
        os.path.join(out_dir, "review-input-bundle.json"), bundle)
    return bundle
