#!/usr/bin/env python3
"""Write a page renewal record (decision D3, 2026-11-01). Report-derived, no edits
to the page.

A renewal record lives beside the pages (pages/renewals/), never inside the
signed page payload. It binds: the page's signed review-payload digest, the
page file digest at renewal time, the drift report it relies on (path and
digest), per source the captured and current raw digests and the normalized
text digests (the identity that matters; wrapper bytes move), the checker, and
the new expiry. Result "unchanged" extends the page's expiry without a human
re-sign; any other result records requires_resign = true and the page stays
ineligible until a human review re-signs changed content.

The answer path honors a record only if its bound digest equals the page's
current signed digest, result is unchanged, requires_resign is false, and the
record's own payload digest recomputes.

Usage: renew_page.py <page_id> [--drift PATH] [--days N] [--on YYYY-MM-DD]
"""
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import answer_path  # noqa: E402

OUT_DIR = ROOT / "pages" / "renewals"


def main(argv):
    if not argv:
        print(__doc__, file=sys.stderr); sys.exit(2)
    page_id = argv[0]
    def arg(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default
    days = int(arg("--days", 90))
    page_path = ROOT / "pages" / f"{page_id}.json"
    page_bytes = page_path.read_bytes()
    page = json.loads(page_bytes)
    if arg("--drift"):
        drift = json.load(open(arg("--drift"), encoding="utf-8"))
        drift["_path"] = str(Path(arg("--drift")).resolve().relative_to(ROOT))
    else:
        drift = answer_path.latest_drift_report()
        if drift is None:
            print("no drift report in sources/watch/", file=sys.stderr); sys.exit(2)
    drift_path = ROOT / drift["_path"]
    rows = {r["source_id"]: r for r in drift["sources"]}
    on = dt.date.fromisoformat(arg("--on") or drift["checked_at"][:10])
    sources, problems = [], []
    for ref in page["source_refs"]:
        r = rows.get(ref["source_id"])
        if r is None:
            problems.append(f"{ref['source_id']}: not in drift report"); continue
        if r["captured_sha256"] != ref["captured_sha256"]:
            problems.append(f"{ref['source_id']}: page binds a different capture than the report checked")
        if r["status"] not in ("unchanged", "unchanged-text"):
            problems.append(f"{ref['source_id']}: {r['status']}")
        sources.append({"source_id": ref["source_id"], "status": r["status"],
                        "captured_sha256": r["captured_sha256"], "current_sha256": r.get("current_sha256"),
                        "captured_normalized_sha256": r.get("captured_normalized_sha256"),
                        "current_normalized_sha256": r.get("current_normalized_sha256"),
                        "current_url": r.get("current_url")})
    result = "unchanged" if not problems else "changed"
    record = {
        "schema_version": "page-renewal/v0.1-interim",
        "renewal_id": f"renewal.{page_id}.{on.isoformat()}",
        "page_id": page_id,
        "page_file": str(page_path.relative_to(ROOT)),
        "page_file_sha256": hashlib.sha256(page_bytes).hexdigest(),
        "bound_review_payload_sha256": page["review_payload"]["sha256"],
        "bound_human_review": [v for v in page["verified"] if v["actor_type"] == "human"],
        "source_check": {"drift_report": drift["_path"],
                         "drift_report_sha256": hashlib.sha256(drift_path.read_bytes()).hexdigest(),
                         "checked_at": drift["checked_at"], "ecfr_current_date": drift["ecfr_current_date"],
                         "comparison": "normalized text (dw-quote-normalization/v0.1); raw digests recorded for provenance",
                         "sources": sources},
        "result": result,
        "problems": problems,
        "checked_by": "process:source_watch/v0.2",
        "renewed_by": "process:renew_page/v0.1",
        "renewed_at": on.isoformat(),
        "previous_stale_after": page["stale_after"],
        "new_stale_after": (on + dt.timedelta(days=days)).isoformat() if result == "unchanged" else page["stale_after"],
        "requires_resign": result != "unchanged",
        "note": "Decision D3 (Skitch, 2026-11-01): unchanged content needs no re-sign; changed content does. This record never alters the signed page payload.",
    }
    record["renewal_payload_sha256"] = answer_path.renewal_payload_hash(record)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{page_id}.renewal-{on.isoformat()}.json"
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"{out.relative_to(ROOT)}: result={result} new_stale_after={record['new_stale_after']} requires_resign={record['requires_resign']}" + (f" problems={problems}" if problems else ""))
    sys.exit(0 if result == "unchanged" else 1)


if __name__ == "__main__":
    main(sys.argv[1:])
