#!/usr/bin/env python3
"""Source watch: refetch a page's sources and compare against registry digests.

For each source_ref on the page, refetches the registry resource URI and
compares the sha256 of the fetched bytes to the registry's captured_sha256.
Updates the page's source_watch block with the dated observation:
  all match      -> last_result "unchanged"
  any mismatch   -> last_result "changed" (change_id lists mismatched sources)
  any fetch fail -> last_result "failed"
The observation is dated, never a live status: readers derive effective
status from evaluation time against next_due_at (ratified fail-closed rule).

Usage: source_watch.py <page.json> <registry.json> [--days-until-due N]
"""
import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone


def main():
    page_path, registry_path = sys.argv[1], sys.argv[2]
    days = 30
    if "--days-until-due" in sys.argv:
        days = int(sys.argv[sys.argv.index("--days-until-due") + 1])
    page = json.load(open(page_path))
    registry = json.load(open(registry_path))
    reg = {s["source_id"]: s for s in registry["sources"]}

    mismatched, failed = [], []
    for ref in page["source_refs"]:
        src = reg[ref["source_id"]]
        try:
            req = urllib.request.Request(
                src["resource"], headers={"User-Agent": "dwtc-source-watch/0.1"})
            body = urllib.request.urlopen(req, timeout=60).read()
        except Exception as exc:
            print(f"FETCH FAILED {src['source_id']}: {exc}", file=sys.stderr)
            failed.append(src["source_id"])
            continue
        digest = hashlib.sha256(body).hexdigest()
        status = "match" if digest == src["captured_sha256"] else "MISMATCH"
        print(f"{src['source_id']}: {status}")
        if status != "match":
            mismatched.append(src["source_id"])

    now = datetime.now(timezone.utc)
    watch = page["source_watch"]
    watch["last_checked_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    watch["next_due_at"] = (now + timedelta(days=days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    if failed:
        watch["last_result"] = "failed"
        watch.pop("change_id", None)
    elif mismatched:
        watch["last_result"] = "changed"
        watch["change_id"] = "changed:" + ",".join(sorted(mismatched))
    else:
        watch["last_result"] = "unchanged"
        watch.pop("change_id", None)
    json.dump(page, open(page_path, "w"), indent=2)
    print(f"source_watch updated: {watch['last_result']}, "
          f"next due {watch['next_due_at']}")
    sys.exit(1 if (failed or mismatched) else 0)


if __name__ == "__main__":
    main()
