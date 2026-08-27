#!/usr/bin/env python3
"""Public, deterministic verifier for Ari's Foundry Pass 2 handoff."""

from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from pathlib import Path


FORBIDDEN_CONTROL_KEYS = {
    "base_natural_record_sha256",
    "certification",
    "error_class",
    "expected_acceptability",
    "mutation_description",
    "source_claim",
    "source_quote",
    "truth_label",
}


def canonical_bytes(value):
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_value(value) -> str:
    return digest_bytes(canonical_bytes(value))


def file_digest(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def require(condition, message):
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from walk_keys(child)


def walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from walk_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_keys(child)


def node_index(tree):
    result = {}
    stack = [tree]
    while stack:
        node = stack.pop()
        result[node["selector"]] = node
        stack.extend(node.get("children", []))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root",
        type=Path,
        required=True,
        help="Checkout containing the bound Pass 2 brief and Pass 1 outputs",
    )
    args = parser.parse_args()
    public_dir = Path(__file__).resolve().parent

    manifest_path = public_dir / "ari-evaluator-public-manifest-v0.1.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest_path.read_bytes() == canonical_bytes(manifest), "manifest is not canonical JSON")

    listed = {member["path"] for member in manifest["members"]}
    actual = {
        path.name
        for path in public_dir.iterdir()
        if path.is_file() and path.name != manifest_path.name
    }
    require(actual == listed, f"manifest member-set mismatch: listed={sorted(listed)} actual={sorted(actual)}")

    for member in manifest["members"]:
        path = public_dir / member["path"]
        require(path.stat().st_size == member["byte_length"], f"byte length mismatch: {path.name}")
        require(file_digest(path) == member["sha256"], f"digest mismatch: {path.name}")
        if path.suffix == ".json":
            value = json.loads(path.read_text(encoding="utf-8"))
            require(path.read_bytes() == canonical_bytes(value), f"non-canonical JSON: {path.name}")
            require(
                all(text == unicodedata.normalize("NFC", text) for text in walk_strings(value)),
                f"non-NFC JSON string: {path.name}",
            )

    brief_path = args.repo_root / "proposals" / "foundry-pass-2-experiment-brief-v0.3.md"
    require(brief_path.is_file(), "bound Pass 2 brief missing")
    require(file_digest(brief_path) == manifest["bindings"]["brief_sha256"], "bound brief digest mismatch")

    contract_path = public_dir / "isolated-reviewer-contract-v0.1.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract_sha = file_digest(contract_path)
    for member_kind in ("system", "task_template"):
        binding = contract["prompts"][member_kind]
        require(file_digest(public_dir / binding["path"]) == binding["sha256"], f"{member_kind} prompt binding mismatch")
    schema_binding = contract["output_schema"]
    require(file_digest(public_dir / schema_binding["path"]) == schema_binding["sha256"], "output-schema binding mismatch")
    require(file_digest(public_dir / schema_binding["validator_path"]) == schema_binding["validator_sha256"], "output-validator binding mismatch")

    controls_path = public_dir / "control-records-v0.1.json"
    controls = json.loads(controls_path.read_text(encoding="utf-8"))
    require(controls["bindings"]["reviewer_contract_sha256"] == contract_sha, "control bundle contract binding mismatch")
    require(controls["count"] == len(controls["records"]) == 21, "control bundle count must be 21")
    leaked = set(walk_keys(controls)) & FORBIDDEN_CONTROL_KEYS
    require(not leaked, f"control metadata leaked into reviewer-visible bundle: {sorted(leaked)}")

    artifact_ids = []
    canonical_cache = {}
    for item in controls["records"]:
        artifact_ids.append(item["artifact_id"])
        core = {
            "claim_payload": item["claim_payload"],
            "declared_section_ambiguities": item["declared_section_ambiguities"],
            "evidence": item["evidence"],
            "normalized_support_anchor_set": item["normalized_support_anchor_set"],
            "source_section": item["source_section"],
        }
        record_sha = digest_value(core)
        require(record_sha == item["record_sha256"], f"record digest mismatch: {item['artifact_id']}")
        require(item["artifact_id"] == f"f2r-{record_sha[:24]}", f"artifact-ID derivation mismatch: {item['artifact_id']}")
        require(digest_value(item["claim_payload"]) == item["claim_payload_sha256"], f"claim digest mismatch: {item['artifact_id']}")
        require(digest_value(item["normalized_support_anchor_set"]) == item["normalized_support_anchor_set_sha256"], f"anchor-set digest mismatch: {item['artifact_id']}")

        evidence_anchors = sorted(
            [entry["support_anchor"] for entry in item["evidence"]],
            key=lambda anchor: (
                anchor["capture_sha256"],
                anchor["selector"],
                anchor["char_start"],
                anchor["char_end"],
                anchor["span_sha256"],
                anchor["logical_anchor"] or "",
            ),
        )
        require(evidence_anchors == item["normalized_support_anchor_set"], f"evidence/anchor mismatch: {item['artifact_id']}")

        section = item["source_section"]
        if section not in canonical_cache:
            canonical_path = args.repo_root / "experiments" / "foundry-pass-1" / "out" / "canonical" / f"section-{section}.json"
            canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
            canonical_cache[section] = (canonical, node_index(canonical["tree"]))
        canonical, nodes = canonical_cache[section]
        for evidence in item["evidence"]:
            anchor = evidence["support_anchor"]
            exact = evidence["exact_text"]
            require(anchor["capture_sha256"] == canonical["capture_sha256"], f"capture binding mismatch: {item['artifact_id']}")
            require(anchor["selector"] in nodes, f"selector missing: {item['artifact_id']}")
            node_text = nodes[anchor["selector"]].get("text", "")
            require(node_text[anchor["char_start"]:anchor["char_end"]] == exact, f"quote span mismatch: {item['artifact_id']}")
            require(digest_bytes(exact.encode("utf-8")) == anchor["span_sha256"], f"quote digest mismatch: {item['artifact_id']}")

    require(len(set(artifact_ids)) == len(artifact_ids), "duplicate control artifact IDs")

    commitment = json.loads((public_dir / "mixed-control-commitment-v0.1.json").read_text(encoding="utf-8"))
    bundle_binding = commitment["bindings"]["control_records_bundle"]
    require(bundle_binding["sha256"] == file_digest(controls_path), "commitment/control bundle digest mismatch")
    require(bundle_binding["byte_length"] == controls_path.stat().st_size, "commitment/control bundle length mismatch")
    require(commitment["bindings"]["reviewer_contract_sha256"] == contract_sha, "commitment/contract mismatch")

    print(
        json.dumps(
            {
                "brief_sha256": manifest["bindings"]["brief_sha256"],
                "control_count": len(controls["records"]),
                "control_records_sha256": file_digest(controls_path),
                "public_manifest_sha256": file_digest(manifest_path),
                "reviewer_contract_sha256": contract_sha,
                "sealed_oracle_byte_length": commitment["sealed_oracle"]["byte_length"],
                "sealed_oracle_sha256": commitment["sealed_oracle"]["sha256"],
                "status": "PASS",
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
