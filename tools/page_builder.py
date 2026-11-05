#!/usr/bin/env python3
"""Shared page-building helpers, lifted unchanged from tools/build_pages_batch1.py (Water Advisor session 5 to 9) so
later batches author pages the same way: every quote is anchored by exact, unique substring search in the quote tool's
normalized capture text; span and review-payload hashes come from quote_tool; pages are written status "draft" with a
process verification only, and Skitch's signature is a separate step. Batch 1's builder keeps its own copy of these
functions on purpose (it is the record of how those pages were made); this module is for Batch 2 onward."""
import datetime as dt, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import quote_tool

REG = {s["source_id"]: s for s in json.load(open(ROOT / "sources/source-registry.dbp-first-proof.json"))["sources"]}
CAP = ROOT / "sources/captures/ecfr-2026-07-01"
NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
DRIFT_CHECKED = "2026-11-02T07:10:07Z"   # sources/watch/drift-2026-10-28.json checked_at
NEXT_DUE = "2026-12-02T07:10:07Z"
STALE_AFTER = "2027-01-31"               # aligned with the two renewed pages and Batch 1
_texts = {}

def text(sec, file=None):
    """Normalized capture text for a section; `file` names the capture when it is not section-<sec>.xml (subpart Q)."""
    if sec not in _texts:
        _texts[sec] = quote_tool.normalized_text(str(CAP / (file or f"section-{sec}.xml")))
    return _texts[sec]

def src_id(sec):
    return "source.ecfr.2026-07-01." + sec.replace(".", "-")

def source_ref(sec):
    s = REG[src_id(sec)]
    return {"source_id": s["source_id"], "captured_sha256": s["captured_sha256"],
            "licensing_decision_payload_sha256": s["reproduction_decision"]["decision_payload_sha256"]}

def quote(page_id, name, sec, needle, file=None):
    t = text(sec, file)
    i = t.find(needle)
    if i < 0:
        sys.exit(f"NOT FOUND in {sec}: {needle[:80]!r}")
    if t.find(needle, i + 1) >= 0:
        sys.exit(f"AMBIGUOUS in {sec}: {needle[:80]!r}")
    return {"quote_id": f"quote.{page_id}.{name}", "source_id": src_id(sec),
            "captured_source_sha256": REG[src_id(sec)]["captured_sha256"],
            "anchor": {"selector_type": "text-position", "selector_version": "v0.1", "value": f"normalized:{i}-{i+len(needle)}"},
            "source_version": "eCFR point-in-time 2026-07-01", "normalization": "dw-quote-normalization/v0.1",
            "span_sha256": quote_tool.span_hash(needle), "verified_at": NOW}

def claim(page_id, name, kind, subject, operator, metric, value, quotes, applicability, conditions=(), exceptions=(), unit=None):
    c = {"claim_id": f"claim.{page_id}.{name}", "kind": kind, "subject": subject,
         "relation": {"operator": operator, "regulatory_metric": metric}, "value": value,
         "conditions": list(conditions), "exceptions": list(exceptions), "jurisdiction": "US-federal",
         "applicability": applicability, "supporting_quote_ids": [f"quote.{page_id}.{q}" for q in dict.fromkeys(quotes)]}
    if unit:
        c["unit"] = unit
    return c

def page(page_id, title, applicability, sections, quotes, claims):
    ids = [q["quote_id"] for q in quotes]
    for c in claims:
        for q in c["supporting_quote_ids"]:
            if q not in ids:
                sys.exit(f"{c['claim_id']} cites a quote that is not on the page: {q}")
    p = {"schema_version": "drinking-water-profile/v0.1", "type": "concept", "page_id": page_id, "title": title,
         "status": "draft", "assurance_profile": "drinking-water/v0.1", "use_class": "regulatory-reference",
         "jurisdiction": "US-federal", "applicability": applicability,
         "generated": {"by": "cc", "at": NOW},
         "review_payload": {"canonicalization": "dw-review-payload/v0.1", "sha256": "0" * 64},
         "normalization": "dw-quote-normalization/v0.1", "verified": [],
         "stale_after": STALE_AFTER,
         "source_watch": {"watch_id": f"watch.{page_id}", "last_result": "unchanged",
                          "last_checked_at": DRIFT_CHECKED, "next_due_at": NEXT_DUE},
         "source_refs": [source_ref(s) for s in sections], "quotes": quotes, "claims": claims}
    h = quote_tool.review_payload_hash(p)
    p["review_payload"]["sha256"] = h
    p["verified"] = [{"by": "process:quote-tool/v0.1-interim", "actor_type": "process", "at": NOW,
                      "review_payload_sha256": h, "scopes": ["source-capture", "quote-fidelity"]}]
    assert quote_tool.review_payload_hash(p) == h
    out = ROOT / "pages" / f"{page_id}.json"
    out.write_text(json.dumps(p, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}: {len(quotes)} quotes, {len(claims)} claims, review sha {h[:12]}")
