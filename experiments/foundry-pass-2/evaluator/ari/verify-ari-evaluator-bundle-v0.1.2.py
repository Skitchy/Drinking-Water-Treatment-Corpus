#!/usr/bin/env python3
"""Public deterministic verifier for Ari's Foundry Pass 2 v0.3 handoff.

The public packet contains commitments only. Pass ``--controls`` when the
private control-record bundle is available to verify its exact bytes and
source bindings. The maintainer may additionally pass ``--oracle`` to verify
the sealed oracle without revealing it to either reviewer or the builder.
"""

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

FORBIDDEN_CONTROL_STRINGS = {
    "certified-correct",
    "deliberately-wrong",
    "numeric-or-unit-substitution",
    "negation",
    "dropped-qualifier",
    "applicability",
    "cross-reference",
    "wrong-anchor-or-context",
    "condition-or-effective-time",
    "accept",
    "reject-or-correct",
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
    """Yield every object key, including objects nested inside arrays."""
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from walk_keys(child)
    elif isinstance(value, list):
        for child in value:
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


def walk_string_values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from walk_string_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_string_values(child)


def verify_no_forbidden_control_keys(controls):
    leaked = set(walk_keys(controls)) & FORBIDDEN_CONTROL_KEYS
    require(
        not leaked,
        f"control metadata leaked into reviewer-visible bundle: {sorted(leaked)}",
    )
    leaked_strings = set(walk_string_values(controls)) & FORBIDDEN_CONTROL_STRINGS
    require(
        not leaked_strings,
        "control truth or stratum strings leaked into reviewer-visible bundle: "
        f"{sorted(leaked_strings)}",
    )


def node_index(tree):
    result = {}
    stack = [tree]
    while stack:
        node = stack.pop()
        result[node["selector"]] = node
        stack.extend(node.get("children", []))
    return result


def verify_public_members(public_dir: Path, manifest):
    listed = [member["path"] for member in manifest["members"]]
    require(len(listed) == len(set(listed)), "duplicate public-manifest member")
    require(
        all(Path(name).name == name for name in listed),
        "public-manifest members must be files in the evaluator directory",
    )
    require(
        "control-records-v0.3.json" not in listed,
        "private control records must not be a public-manifest member",
    )

    for member in manifest["members"]:
        path = public_dir / member["path"]
        require(path.is_file(), f"public member missing: {path.name}")
        require(
            path.stat().st_size == member["byte_length"],
            f"byte length mismatch: {path.name}",
        )
        require(
            file_digest(path) == member["sha256"],
            f"digest mismatch: {path.name}",
        )
        if path.suffix == ".json":
            value = json.loads(path.read_text(encoding="utf-8"))
            require(
                path.read_bytes() == canonical_bytes(value),
                f"non-canonical JSON: {path.name}",
            )
            require(
                all(
                    text == unicodedata.normalize("NFC", text)
                    for text in walk_strings(value)
                ),
                f"non-NFC JSON string: {path.name}",
            )


def verify_control_records(
    controls_path: Path,
    repo_root: Path,
    commitment,
    contract_sha: str,
    brief_sha: str,
):
    binding = commitment["bindings"]["control_records_bundle"]
    require(
        controls_path.stat().st_size == binding["byte_length"],
        "private control-bundle byte length mismatch",
    )
    require(
        file_digest(controls_path) == binding["sha256"],
        "private control-bundle digest mismatch",
    )
    controls = json.loads(controls_path.read_text(encoding="utf-8"))
    require(
        controls_path.read_bytes() == canonical_bytes(controls),
        "private control bundle is not canonical JSON",
    )
    require(
        controls["bindings"]["reviewer_contract_sha256"] == contract_sha,
        "control bundle contract binding mismatch",
    )
    require(
        controls["bindings"]["brief_sha256"] == brief_sha,
        "control bundle brief binding mismatch",
    )
    expected_count = commitment["counts"]["total"]
    require(
        controls["count"] == len(controls["records"]) == expected_count,
        f"control bundle count must be {expected_count}",
    )
    verify_no_forbidden_control_keys(controls)

    artifact_ids = []
    canonical_cache = {}
    for item in controls["records"]:
        artifact_ids.append(item["artifact_id"])
        core = {
            "claim_payload": item["claim_payload"],
            "declared_section_ambiguities": item["declared_section_ambiguities"],
            "evidence": item["evidence"],
            "normalized_support_anchor_set": item[
                "normalized_support_anchor_set"
            ],
            "source_section": item["source_section"],
        }
        record_sha = digest_value(core)
        require(
            record_sha == item["record_sha256"],
            f"record digest mismatch: {item['artifact_id']}",
        )
        require(
            item["artifact_id"] == f"f2r-{record_sha[:24]}",
            f"artifact-ID derivation mismatch: {item['artifact_id']}",
        )
        require(
            digest_value(item["claim_payload"])
            == item["claim_payload_sha256"],
            f"claim digest mismatch: {item['artifact_id']}",
        )
        require(
            digest_value(item["normalized_support_anchor_set"])
            == item["normalized_support_anchor_set_sha256"],
            f"anchor-set digest mismatch: {item['artifact_id']}",
        )

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
        require(
            evidence_anchors == item["normalized_support_anchor_set"],
            f"evidence/anchor mismatch: {item['artifact_id']}",
        )

        section = item["source_section"]
        if section not in canonical_cache:
            canonical_path = (
                repo_root
                / "experiments"
                / "foundry-pass-1"
                / "out"
                / "canonical"
                / f"section-{section}.json"
            )
            canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
            canonical_cache[section] = (canonical, node_index(canonical["tree"]))
        canonical, nodes = canonical_cache[section]
        for evidence in item["evidence"]:
            anchor = evidence["support_anchor"]
            exact = evidence["exact_text"]
            require(
                anchor["capture_sha256"] == canonical["capture_sha256"],
                f"capture binding mismatch: {item['artifact_id']}",
            )
            require(
                anchor["selector"] in nodes,
                f"selector missing: {item['artifact_id']}",
            )
            node_text = nodes[anchor["selector"]].get("text", "")
            require(
                node_text[anchor["char_start"] : anchor["char_end"]] == exact,
                f"quote span mismatch: {item['artifact_id']}",
            )
            require(
                digest_bytes(exact.encode("utf-8")) == anchor["span_sha256"],
                f"quote digest mismatch: {item['artifact_id']}",
            )

    require(
        len(set(artifact_ids)) == len(artifact_ids),
        "duplicate control artifact IDs",
    )
    return controls


def verify_oracle(oracle_path: Path, controls, commitment, contract_sha, brief_sha):
    raw = oracle_path.read_bytes()
    sealed = commitment["sealed_oracle"]
    require(len(raw) == sealed["byte_length"], "sealed-oracle byte length mismatch")
    require(digest_bytes(raw) == sealed["sha256"], "sealed-oracle digest mismatch")
    oracle = json.loads(raw)
    require(raw == canonical_bytes(oracle), "sealed oracle is not canonical JSON")
    require(
        oracle["bindings"]["brief_sha256"] == brief_sha,
        "oracle brief binding mismatch",
    )
    require(
        oracle["bindings"]["reviewer_contract_sha256"] == contract_sha,
        "oracle contract binding mismatch",
    )
    control_binding = oracle["bindings"]["control_records_bundle"]
    require(
        control_binding["sha256"]
        == commitment["bindings"]["control_records_bundle"]["sha256"],
        "oracle control-bundle digest mismatch",
    )
    require(
        oracle["grading"]["thresholds"] == commitment["thresholds"],
        "oracle/commitment threshold mismatch",
    )

    records = {record["artifact_id"]: record for record in controls["records"]}
    entries = oracle["controls"]
    require(len(entries) == len(records), "oracle/control count mismatch")
    require(
        {entry["artifact_id"] for entry in entries} == set(records),
        "oracle/control identity-set mismatch",
    )
    class_counts = {}
    truth_counts = {}
    for entry in entries:
        record = records[entry["artifact_id"]]
        for field in (
            "record_sha256",
            "claim_payload_sha256",
            "normalized_support_anchor_set_sha256",
        ):
            require(
                entry[field] == record[field],
                f"oracle record binding mismatch: {field}",
            )
        truth = entry["truth_label"]
        error_class = entry["error_class"]
        truth_counts[truth] = truth_counts.get(truth, 0) + 1
        class_counts.setdefault(error_class, {})[truth] = (
            class_counts.setdefault(error_class, {}).get(truth, 0) + 1
        )

    counts = commitment["counts"]
    require(
        truth_counts.get("certified-correct", 0) == counts["certified_correct"],
        "oracle certified-correct count mismatch",
    )
    require(
        truth_counts.get("deliberately-wrong", 0) == counts["deliberately_wrong"],
        "oracle deliberately-wrong count mismatch",
    )
    require(set(class_counts) == set(counts["error_classes"]), "oracle class-set mismatch")
    for error_class in counts["error_classes"]:
        require(
            class_counts[error_class].get("certified-correct", 0)
            == counts["certified_correct_per_error_class"],
            f"oracle positive stratum mismatch: {error_class}",
        )
        require(
            class_counts[error_class].get("deliberately-wrong", 0)
            == counts["deliberately_wrong_per_error_class"],
            f"oracle wrong stratum mismatch: {error_class}",
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument(
        "--controls",
        type=Path,
        help="Private control-record bundle; identities remain withheld publicly",
    )
    parser.add_argument(
        "--oracle",
        type=Path,
        help="Sealed oracle; maintainer-only until reviewer outputs are fixed",
    )
    args = parser.parse_args()
    require(not args.oracle or args.controls, "--oracle requires --controls")

    public_dir = Path(__file__).resolve().parent
    manifest_path = public_dir / "ari-evaluator-public-manifest-v0.3.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(
        manifest_path.read_bytes() == canonical_bytes(manifest),
        "manifest is not canonical JSON",
    )
    verify_public_members(public_dir, manifest)

    brief_binding = manifest["bindings"]["brief"]
    brief_path = args.repo_root / brief_binding["path"]
    require(brief_path.is_file(), "bound Pass 2 brief missing")
    require(
        file_digest(brief_path) == brief_binding["sha256"],
        "bound brief digest mismatch",
    )

    contract_path = public_dir / "isolated-reviewer-contract-v0.3.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract_sha = file_digest(contract_path)
    require(
        contract["bindings"]["brief_sha256"] == brief_binding["sha256"],
        "contract/brief binding mismatch",
    )
    for member_kind in ("system", "task_template"):
        binding = contract["prompts"][member_kind]
        require(
            file_digest(public_dir / binding["path"]) == binding["sha256"],
            f"{member_kind} prompt binding mismatch",
        )
    schema_binding = contract["output_schema"]
    require(
        file_digest(public_dir / schema_binding["path"])
        == schema_binding["sha256"],
        "output-schema binding mismatch",
    )
    require(
        file_digest(public_dir / schema_binding["validator_path"])
        == schema_binding["validator_sha256"],
        "output-validator binding mismatch",
    )

    commitment_path = public_dir / "mixed-control-commitment-v0.3.json"
    commitment = json.loads(commitment_path.read_text(encoding="utf-8"))
    require(
        commitment["bindings"]["brief_sha256"] == brief_binding["sha256"],
        "commitment/brief binding mismatch",
    )
    require(
        commitment["bindings"]["reviewer_contract_sha256"] == contract_sha,
        "commitment/contract mismatch",
    )
    require(
        commitment["bindings"]["public_bundle_verifier_sha256"]
        == file_digest(Path(__file__)),
        "commitment/verifier mismatch",
    )

    controls = None
    if args.controls:
        controls = verify_control_records(
            args.controls,
            args.repo_root,
            commitment,
            contract_sha,
            brief_binding["sha256"],
        )
    if args.oracle:
        verify_oracle(
            args.oracle,
            controls,
            commitment,
            contract_sha,
            brief_binding["sha256"],
        )

    if args.oracle:
        status = "PASS_FULL_PACKET"
        verification_scope = "public commitments, private controls, and sealed oracle"
    elif args.controls:
        status = "PASS_PRIVATE_CONTROLS"
        verification_scope = "public commitments and private controls"
    else:
        status = "PASS_PUBLIC_ONLY"
        verification_scope = "public commitments only"

    print(
        json.dumps(
            {
                "brief_sha256": brief_binding["sha256"],
                "control_count": commitment["counts"]["total"],
                "control_records_sha256": commitment["bindings"][
                    "control_records_bundle"
                ]["sha256"],
                "private_controls_status": "VERIFIED"
                if args.controls
                else "NOT_PROVIDED",
                "public_manifest_sha256": file_digest(manifest_path),
                "reviewer_contract_sha256": contract_sha,
                "sealed_oracle_byte_length": commitment["sealed_oracle"][
                    "byte_length"
                ],
                "sealed_oracle_sha256": commitment["sealed_oracle"]["sha256"],
                "sealed_oracle_status": "VERIFIED"
                if args.oracle
                else "NOT_PROVIDED",
                "status": status,
                "verification_scope": verification_scope,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
