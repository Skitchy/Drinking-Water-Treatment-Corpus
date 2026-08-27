#!/usr/bin/env python3
"""Deterministically grade fixed reviewer outputs after oracle reveal."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def canonical_bytes(value):
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_outputs(path: Path):
    paths = sorted(path.glob("*.json")) if path.is_dir() else [path]
    dispositions = {}
    duplicates = []
    output_digests = []
    for item_path in paths:
        raw = item_path.read_bytes()
        output_digests.append({"path": item_path.name, "sha256": digest_bytes(raw)})
        value = json.loads(raw)
        objects = value if isinstance(value, list) else [value]
        for obj in objects:
            for disposition in obj["dispositions"]:
                artifact_id = disposition["artifact_id"]
                if artifact_id in dispositions:
                    duplicates.append(artifact_id)
                else:
                    dispositions[artifact_id] = disposition
    return dispositions, sorted(set(duplicates)), output_digests


def is_bound_accept(disposition, oracle_entry):
    return bool(
        disposition
        and disposition.get("verdict") == "accept"
        and disposition.get("record_sha256") == oracle_entry["record_sha256"]
        and disposition.get("claim_payload_sha256") == oracle_entry["claim_payload_sha256"]
        and disposition.get("normalized_support_anchor_set_sha256")
        == oracle_entry["normalized_support_anchor_set_sha256"]
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--reviewer-a", type=Path, required=True)
    parser.add_argument("--reviewer-b", type=Path, required=True)
    args = parser.parse_args()

    oracle_raw = args.oracle.read_bytes()
    oracle = json.loads(oracle_raw)
    reviewer_a, duplicates_a, output_digests_a = load_outputs(args.reviewer_a)
    reviewer_b, duplicates_b, output_digests_b = load_outputs(args.reviewer_b)
    entries = {entry["artifact_id"]: entry for entry in oracle["controls"]}
    control_ids = set(entries)

    missing_a = sorted(control_ids - set(reviewer_a))
    missing_b = sorted(control_ids - set(reviewer_b))
    correct_ids = {
        artifact_id
        for artifact_id, entry in entries.items()
        if entry["truth_label"] == "certified-correct"
    }
    wrong_ids = control_ids - correct_ids

    accepted_a = {
        artifact_id
        for artifact_id, entry in entries.items()
        if is_bound_accept(reviewer_a.get(artifact_id), entry)
    }
    accepted_b = {
        artifact_id
        for artifact_id, entry in entries.items()
        if is_bound_accept(reviewer_b.get(artifact_id), entry)
    }
    unanimous = accepted_a & accepted_b

    metrics = {
        "control_disposition_missing_or_duplicate": len(missing_a) + len(missing_b) + len(duplicates_a) + len(duplicates_b),
        "reviewer_a_certified_correct_accept": len(accepted_a & correct_ids),
        "reviewer_a_deliberately_wrong_accept": len(accepted_a & wrong_ids),
        "reviewer_b_certified_correct_accept": len(accepted_b & correct_ids),
        "reviewer_b_deliberately_wrong_accept": len(accepted_b & wrong_ids),
        "unanimously_accepted_certified_correct": len(unanimous & correct_ids),
        "unanimously_accepted_deliberately_wrong": len(unanimous & wrong_ids),
    }
    thresholds = oracle["grading"]["thresholds"]
    gates = {
        "complete_control_dispositions": metrics["control_disposition_missing_or_duplicate"] <= thresholds["control_disposition_missing_or_duplicate_max"],
        "reviewer_a_positive_floor": metrics["reviewer_a_certified_correct_accept"] >= thresholds["per_reviewer_certified_correct_accept_min"],
        "reviewer_a_wrong_accept_ceiling": metrics["reviewer_a_deliberately_wrong_accept"] <= thresholds["per_reviewer_deliberately_wrong_accept_max"],
        "reviewer_b_positive_floor": metrics["reviewer_b_certified_correct_accept"] >= thresholds["per_reviewer_certified_correct_accept_min"],
        "reviewer_b_wrong_accept_ceiling": metrics["reviewer_b_deliberately_wrong_accept"] <= thresholds["per_reviewer_deliberately_wrong_accept_max"],
        "unanimous_positive_floor": metrics["unanimously_accepted_certified_correct"] >= thresholds["unanimously_accepted_certified_correct_min"],
        "unanimous_wrong_accept_ceiling": metrics["unanimously_accepted_deliberately_wrong"] <= thresholds["unanimously_accepted_deliberately_wrong_max"],
    }
    result = {
        "artifact_version": "foundry-pass-2-control-grading/experimental-v0.1",
        "gates": gates,
        "hard_gate_result": "PASS" if all(gates.values()) else "FAIL",
        "metrics": metrics,
        "oracle_sha256": digest_bytes(oracle_raw),
        "reviewer_a_output_digests": output_digests_a,
        "reviewer_b_output_digests": output_digests_b,
        "thresholds": thresholds,
    }
    print(canonical_bytes(result).decode("utf-8"), end="")


if __name__ == "__main__":
    main()
