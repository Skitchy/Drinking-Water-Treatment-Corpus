#!/usr/bin/env python3
"""Source watch, drift mode (report only).

The previous version refetched each registry resource, which is a point-in-time
eCFR URL (2026-07-01). That URL cannot change, so it could never detect drift.
This version compares every captured eCFR section against the CURRENT eCFR
text and reports per section. It edits nothing: no pages/, no stale_after, no
registry. Renewal is Batch 0 work under decision D3.

How "current" is found: the eCFR versioner publishes titles.json with a
latest_issue_date per title; the full-text endpoint 404s for dates after that,
so the current text is fetched at that date, which is recorded in the report.
The endpoint also requires Accept-Encoding: gzip.

Per-section results:
  unchanged      current bytes equal the captured bytes (sha256)
  unchanged-text bytes differ but the normalized text (dw-quote-normalization/
                 v0.1, same as the pages) is identical: wrapper-only change
  changed        normalized text differs; a short unified diff is reported
  fetch-failed   HTTP or transport error; fails closed (nonzero exit)
  not-watched    non-eCFR source (the EPA guide); reported, not compared

Usage:
  source_watch.py drift [--registry PATH] [--captures DIR] [--out report.json]
                        [--date YYYY-MM-DD] [--max-diff-lines N]
      default --out: sources/watch/drift-<checked-at-utc>-ecfr-<ecfr-date>.json
      (committed; the answer path reads the newest by checked_at as the live
      watch result; naming by check time means no same-day overwrite)
  source_watch.py selftest      # offline: proves changed and fetch-failed are caught
Exit: 0 all unchanged (or unchanged-text); 1 any changed; 2 any fetch failure.
"""
import difflib
import gzip
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import quote_tool  # noqa: E402

TITLES_URL = "https://www.ecfr.gov/api/versioner/v1/titles.json"
UA = "dwtc-source-watch/0.2"
DATE_RE = re.compile(r"/full/(\d{4}-\d{2}-\d{2})/")


def http_get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        if resp.headers.get("Content-Encoding", "") == "gzip":
            body = gzip.decompress(body)
        return body


def latest_issue_date(fetch=http_get):
    data = json.loads(fetch(TITLES_URL))
    for t in data["titles"]:
        if t["number"] == 40:
            return t["latest_issue_date"]
    raise RuntimeError("title 40 not in titles.json")


def capture_file(source, captures_dir):
    m = re.search(r"section=([0-9.]+)", source["resource"])
    if m:
        return captures_dir / "ecfr-2026-07-01" / f"section-{m.group(1)}.xml"
    if "subpart=Q" in source["resource"]:
        return captures_dir / "ecfr-2026-07-01" / "subpart-Q.xml"
    return None


def normalized_from_bytes(xml_bytes):
    from xml.etree import ElementTree
    root = ElementTree.fromstring(xml_bytes)
    return re.sub(r"\s+", " ", "".join(root.itertext())).strip()


def check_source(source, captures_dir, current_date, fetch=http_get, max_diff_lines=20):
    sid = source["source_id"]
    cap = capture_file(source, captures_dir)
    if cap is None:
        return {"source_id": sid, "status": "not-watched", "note": "non-eCFR source; not compared"}
    cap_bytes = cap.read_bytes()
    row = {"source_id": sid, "capture_file": str(cap.relative_to(ROOT)),
           "captured_sha256": hashlib.sha256(cap_bytes).hexdigest()}
    if row["captured_sha256"] != source["captured_sha256"]:
        row.update(status="changed", note="capture file digest does not match the registry")
        return row
    url = DATE_RE.sub(f"/full/{current_date}/", source["resource"])
    row["current_url"] = url
    try:
        cur = fetch(url)
    except Exception as exc:  # fail closed: a watch that cannot see the source is a failed watch
        row.update(status="fetch-failed", error=f"{type(exc).__name__}: {exc}")
        return row
    row["current_sha256"] = hashlib.sha256(cur).hexdigest()
    try:
        a = normalized_from_bytes(cap_bytes)
        b = a if row["current_sha256"] == row["captured_sha256"] else normalized_from_bytes(cur)
    except Exception as exc:
        row.update(status="fetch-failed", error=f"unparseable current XML: {exc}")
        return row
    # normalized-text digests are what a renewal record binds to (D3): wrapper
    # bytes move (subpart Q VOLUME attribute), regulation text is the identity
    row["captured_normalized_sha256"] = hashlib.sha256(a.encode("utf-8")).hexdigest()
    row["current_normalized_sha256"] = hashlib.sha256(b.encode("utf-8")).hexdigest()
    if row["current_sha256"] == row["captured_sha256"]:
        row["status"] = "unchanged"
        return row
    if a == b:
        row.update(status="unchanged-text", note="bytes differ, normalized text identical")
        return row
    diff = list(difflib.unified_diff(a.split(". "), b.split(". "), "captured", "current", lineterm="", n=1))
    row.update(status="changed", diff=diff[:max_diff_lines], diff_lines_total=len(diff))
    return row


def drift(argv):
    def arg(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default
    registry = json.load(open(arg("--registry", ROOT / "sources" / "source-registry.dbp-first-proof.json"), encoding="utf-8"))
    captures_dir = Path(arg("--captures", ROOT / "sources" / "captures"))
    max_lines = int(arg("--max-diff-lines", 20))
    checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        current_date = arg("--date") or latest_issue_date()
    except Exception as exc:
        print(f"FETCH FAILED titles.json: {exc}", file=sys.stderr)
        sys.exit(2)
    rows = [check_source(s, captures_dir, current_date, max_diff_lines=max_lines) for s in registry["sources"]]
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    report = {"mode": "drift-report-only", "checked_at": checked_at, "ecfr_current_date": current_date,
              "capture_point_in_time": "2026-07-01", "registry_id": registry["registry_id"],
              "counts": counts, "sources": rows}
    # named by CHECK time, not eCFR date: a second same-day check never overwrites
    # a file a renewal record binds by digest (session-3 open issue)
    out = Path(arg("--out") or (ROOT / "sources" / "watch" / f"drift-{checked_at.replace(':', '').replace('-', '')}-ecfr-{current_date}.json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"report written: {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    print(f"source watch drift report, checked {checked_at}, current eCFR date {current_date}")
    for r in rows:
        print(f"  {r['status']:15s} {r['source_id']}" + (f"  {r.get('note') or r.get('error') or ''}" if r['status'] not in ('unchanged',) else ""))
        for line in r.get("diff", [])[:max_lines]:
            print("      " + line)
    print("  counts:", counts)
    sys.exit(2 if counts.get("fetch-failed") else (1 if counts.get("changed") else 0))


def selftest():
    """Offline. A changed current text must be reported as changed with a diff;
    a fetch error must be reported as fetch-failed; identical bytes unchanged."""
    registry = json.load(open(ROOT / "sources" / "source-registry.dbp-first-proof.json", encoding="utf-8"))
    src = next(s for s in registry["sources"] if s["source_id"] == "source.ecfr.2026-07-01.141-53")
    cap_bytes = capture_file(src, ROOT / "sources" / "captures").read_bytes()
    results = []
    r = check_source(src, ROOT / "sources" / "captures", "2099-01-01", fetch=lambda u: cap_bytes)
    results.append(("identical bytes -> unchanged", r["status"] == "unchanged"))
    results.append(("normalized digests recorded and equal", r.get("captured_normalized_sha256") and r["captured_normalized_sha256"] == r["current_normalized_sha256"]))
    results.append(("current url uses the current date", "/full/2099-01-01/" in r["current_url"]))
    assert b"Bromate" in cap_bytes
    mutated = cap_bytes.replace(b"Bromate", b"Bromite", 1)
    r = check_source(src, ROOT / "sources" / "captures", "2099-01-01", fetch=lambda u: mutated)
    results.append(("edited text -> changed with diff", r["status"] == "changed" and any("Bromite" in l for l in r["diff"])))
    wrapper = cap_bytes.replace(b'TYPE="SECTION"', b'TYPE="SECTION" extra="1"', 1)
    r = check_source(src, ROOT / "sources" / "captures", "2099-01-01", fetch=lambda u: wrapper)
    results.append(("wrapper-only change -> unchanged-text", r["status"] == "unchanged-text"))
    def boom(u):
        raise urllib.error.URLError("simulated outage")
    r = check_source(src, ROOT / "sources" / "captures", "2099-01-01", fetch=boom)
    results.append(("fetch error -> fetch-failed (fail closed)", r["status"] == "fetch-failed"))
    r = check_source(src, ROOT / "sources" / "captures", "2099-01-01", fetch=lambda u: b"<not xml")
    results.append(("unparseable current -> fetch-failed", r["status"] == "fetch-failed"))
    epa = next(s for s in registry["sources"] if s["source_id"].startswith("source.epa"))
    r = check_source(epa, ROOT / "sources" / "captures", "2099-01-01", fetch=boom)
    results.append(("non-eCFR source -> not-watched, no fetch", r["status"] == "not-watched"))
    for name, ok in results:
        print(("PASS " if ok else "FAIL ") + name)
    return all(ok for _, ok in results)


def main(argv):
    if argv[:1] == ["drift"]:
        drift(argv[1:])
    elif argv[:1] == ["selftest"]:
        sys.exit(0 if selftest() else 1)
    else:
        print(__doc__, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv[1:])
