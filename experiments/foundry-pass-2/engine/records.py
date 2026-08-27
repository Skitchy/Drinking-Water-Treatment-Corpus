"""Canonical claim-and-evidence records, per Ari's isolated-reviewer
contract "canonicalization" (c530b860...), built from adapter Candidates.

record core   = {claim_payload, declared_section_ambiguities, evidence,
                 normalized_support_anchor_set, source_section}
record_sha256 = sha256(canonical_bytes(core))
artifact_id   = "f2r-" + record_sha256[:24]
claim_payload_sha256 / normalized_support_anchor_set_sha256 likewise.

The field name source_section is the contract's, kept verbatim so control
records and natural records canonicalize identically; the engine treats it
as the opaque unit id it is.
"""

from . import canon
from .contract import validate_candidate, ContractError

ANCHOR_SORT_KEY = ("capture_sha256", "selector", "char_start", "char_end",
                   "span_sha256", "logical_anchor")


def normalize_anchor_set(evidence):
    """Sorted list of support anchors; logical_anchor null sorts as ''."""
    anchors = [e["support_anchor"] for e in evidence]
    return sorted(anchors, key=lambda a: tuple(
        (a[k] if a[k] is not None else "") for k in ANCHOR_SORT_KEY))


def build_record(candidate, unit_ambiguities):
    validate_candidate(candidate)
    payload = canon.nfc(candidate["claim_payload"])
    evidence = canon.nfc([
        {"exact_text": e["exact_text"],
         "support_anchor": dict(e["support_anchor"])}
        for e in candidate["evidence"]])
    anchor_set = normalize_anchor_set(evidence)
    core = {
        "claim_payload": payload,
        "declared_section_ambiguities": canon.nfc(list(unit_ambiguities)),
        "evidence": evidence,
        "normalized_support_anchor_set": anchor_set,
        "source_section": candidate["unit_id"],
    }
    record_sha = canon.content_digest(core)
    record = dict(core)
    record["record_sha256"] = record_sha
    record["artifact_id"] = "f2r-" + record_sha[:24]
    record["claim_payload_sha256"] = canon.content_digest(payload)
    record["normalized_support_anchor_set_sha256"] = \
        canon.content_digest(anchor_set)
    return record


def _node_index(representation):
    index = {}
    stack = [representation]
    while stack:
        node = stack.pop()
        index[node["selector"]] = node
        stack.extend(node.get("children", []))
    return index


def verify_record(record, unit):
    """Recompute every digest and rebind every quote against the unit's
    canonical representation. Returns a verification record; never raises
    for a content failure, only for a contract violation."""
    core = {k: record[k] for k in (
        "claim_payload", "declared_section_ambiguities", "evidence",
        "normalized_support_anchor_set", "source_section")}
    problems = []
    record_sha = canon.content_digest(core)
    if record_sha != record["record_sha256"]:
        problems.append("record-digest-mismatch")
    if record["artifact_id"] != "f2r-" + record_sha[:24]:
        problems.append("artifact-id-derivation-mismatch")
    if canon.content_digest(record["claim_payload"]) != \
            record["claim_payload_sha256"]:
        problems.append("payload-digest-mismatch")
    if canon.content_digest(record["normalized_support_anchor_set"]) != \
            record["normalized_support_anchor_set_sha256"]:
        problems.append("anchor-set-digest-mismatch")
    if normalize_anchor_set(record["evidence"]) != \
            record["normalized_support_anchor_set"]:
        problems.append("anchor-set-not-normalized")
    if record["source_section"] != unit["unit_id"]:
        problems.append("unit-mismatch")
    nodes = _node_index(unit["representation"])
    root_link = unit["anchor_rules"]["custody"][0]
    root_digest = unit[root_link["digest_field"]]
    for entry in record["evidence"]:
        anchor = entry["support_anchor"]
        exact = entry["exact_text"]
        if anchor["capture_sha256"] != root_digest:
            problems.append("custody-root-mismatch")
            continue
        node = nodes.get(anchor["selector"])
        if node is None:
            problems.append("selector-not-found")
            continue
        text = node.get("text", "")
        if text[anchor["char_start"]:anchor["char_end"]] != exact:
            problems.append("quote-span-mismatch")
        if canon.bytes_digest(exact.encode("utf-8")) != anchor["span_sha256"]:
            problems.append("quote-digest-mismatch")
    return {
        "artifact_id": record["artifact_id"],
        "record_sha256": record["record_sha256"],
        "verdict": "verified" if not problems else "failed",
        "problems": sorted(set(problems)),
    }
