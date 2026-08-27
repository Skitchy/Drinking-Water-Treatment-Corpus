"""Stage 4: machine verification of extraction candidates.

Selection, not authorship: every candidate quote must resolve
character-exactly against the canonical representation; every claim must be
supported by a verified quote containing its value verbatim. Failures are
recorded, never repaired silently. The only declared normalization applied
to raw model output is code-fence stripping, counted as a machine
correction.

Usage: python3 verify_candidates.py [section ...]   (default: all pending)
"""

import hashlib
import json
import os
import sys

import foundry_lib

COMPILER_DIR = os.path.dirname(os.path.abspath(__file__))
EXPERIMENT_DIR = os.path.dirname(COMPILER_DIR)
REPO_ROOT = os.path.dirname(os.path.dirname(EXPERIMENT_DIR))
OUT_DIR = os.path.join(EXPERIMENT_DIR, "out")

ALLOWED_RELATIONS = {
    "has-mcl", "has-mclg", "has-mrdl", "has-mrdlg", "requires-monitoring",
    "compliance-basis", "applies-to", "defined-as",
    "requires-treatment-technique",
}
ALLOWED_KINDS = {"numeric", "qualitative", "table-cell"}


def strip_fences(text):
    """Declared normalization: strip one leading/trailing markdown code
    fence pair. Returns (stripped_text, was_corrected)."""
    stripped = text.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        if first_newline != -1 and stripped.endswith("```"):
            return stripped[first_newline + 1:-3].strip(), True
    return stripped, False


def build_node_index(tree):
    index = {}
    stack = [tree]
    while stack:
        node = stack.pop()
        index[node["selector"]] = node
        stack.extend(node.get("children", []))
    return index


def verify_section(section_number):
    candidate_path = os.path.join(
        OUT_DIR, "candidates", f"candidate-{section_number}.json")
    record = json.load(open(candidate_path))
    canonical = json.load(open(os.path.join(
        OUT_DIR, "canonical", f"section-{section_number}.json")))
    nodes = build_node_index(canonical["tree"])
    anchor_by_selector = {
        a["selector"]: a for a in canonical["logical_anchors"]}

    report = {
        "section_number": section_number,
        "candidate_response_sha256": record["response_sha256"],
        "machine_corrections": [],
        "verified_quotes": [], "rejected_quotes": [],
        "verified_claims": [], "rejected_claims": [],
        "page_proposals": [], "challenge_questions": [],
        "rejected_questions": [], "ambiguities_declared": [],
    }

    text, corrected = strip_fences(record["raw_response"])
    if corrected:
        report["machine_corrections"].append("stripped-code-fence")
    try:
        candidate = json.loads(text)
    except json.JSONDecodeError as err:
        report["parse_verdict"] = f"rejected-unparseable: {err}"
        return _finish(report, section_number)
    report["parse_verdict"] = "parsed"
    report["ambiguities_declared"] = candidate.get("ambiguities", [])

    quote_text_by_id = {}
    for quote in candidate.get("quotes", []):
        quote_id = quote.get("candidate_quote_id", "?")
        selector = quote.get("selector", "")
        exact = quote.get("exact_text", "")
        node = nodes.get(selector)
        if node is None:
            report["rejected_quotes"].append(
                {"id": quote_id, "reason": "selector-not-found",
                 "selector": selector})
            continue
        node_text = node.get("text", "")
        position = node_text.find(exact) if exact else -1
        if position == -1:
            report["rejected_quotes"].append(
                {"id": quote_id, "reason": "text-not-contiguous-in-node",
                 "selector": selector})
            continue
        span_sha = hashlib.sha256(exact.encode("utf-8")).hexdigest()
        anchor = anchor_by_selector.get(selector, {})
        report["verified_quotes"].append({
            "id": quote_id,
            "binding": {
                "capture_sha256": canonical["capture_sha256"],
                "selector": selector,
                "char_start": position,
                "char_end": position + len(exact),
                "span_sha256": span_sha,
            },
            "logical_anchor": anchor.get("label") if
                anchor.get("status") == "derived" else None,
            "exact_text": exact,
        })
        quote_text_by_id[quote_id] = exact

    for claim in candidate.get("claims", []):
        claim_id = claim.get("candidate_claim_id", "?")
        problems = []
        if claim.get("kind") not in ALLOWED_KINDS:
            problems.append(f"kind-not-allowed:{claim.get('kind')}")
        if claim.get("relation") not in ALLOWED_RELATIONS:
            problems.append(f"relation-not-controlled:{claim.get('relation')}")
        supports = claim.get("supporting_quotes", [])
        resolved = [quote_text_by_id[q] for q in supports
                    if q in quote_text_by_id]
        if not supports or len(resolved) != len(supports):
            problems.append("supporting-quote-unresolved")
        else:
            value = str(claim.get("value", ""))
            if value and not any(value in text for text in resolved):
                problems.append("value-not-verbatim-in-support")
        if problems:
            report["rejected_claims"].append(
                {"id": claim_id, "reasons": problems, "claim": claim})
        else:
            report["verified_claims"].append(claim)

    for proposal in candidate.get("page_proposals", []):
        ok = bool(proposal.get("candidate_page_id")) and \
            bool(proposal.get("topic"))
        proposal["shape_verdict"] = "accepted" if ok else "rejected"
        report["page_proposals"].append(proposal)

    for question in candidate.get("challenge_questions", []):
        selectors = question.get("evidence_selectors", [])
        if selectors and all(s in nodes for s in selectors):
            report["challenge_questions"].append(question)
        else:
            report["rejected_questions"].append(
                {"question": question,
                 "reason": "evidence-selector-unresolved"})

    return _finish(report, section_number)


def _finish(report, section_number):
    counts = {
        "quotes_verified": len(report["verified_quotes"]),
        "quotes_rejected": len(report["rejected_quotes"]),
        "claims_verified": len(report["verified_claims"]),
        "claims_rejected": len(report["rejected_claims"]),
        "questions_kept": len(report["challenge_questions"]),
        "questions_rejected": len(report["rejected_questions"]),
    }
    report["counts"] = counts
    foundry_lib.write_canonical(
        os.path.join(OUT_DIR, "verified",
                     f"verified-{section_number}.json"), report)
    return counts


def main():
    candidates_dir = os.path.join(OUT_DIR, "candidates")
    requested = sys.argv[1:]
    sections = requested or sorted(
        name.replace("candidate-", "").replace(".json", "")
        for name in os.listdir(candidates_dir)
        if name.startswith("candidate-"))
    for section_number in sections:
        counts = verify_section(section_number)
        print(section_number, json.dumps(counts, sort_keys=True))


if __name__ == "__main__":
    main()
