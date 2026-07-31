#!/usr/bin/env python3
"""Quote extraction and hashing under the INTERIM dw-quote-normalization/v0.1.

Interim normalization (flagged for replacement by the ratified spec):
  1. Parse the captured XML file; take the text content of the document in
     order (XML tags stripped, entities resolved).
  2. Collapse every run of whitespace to a single space; strip leading and
     trailing whitespace.
  3. Anchors are character offsets into that normalized stream, expressed as
     "normalized:<start>-<end>". span_sha256 is the sha256 of the UTF-8
     encoding of the quoted span.

Also computes the INTERIM dw-review-payload/v0.1 digest: the page object
minus review_payload, verified, generated, source_watch, and status fields,
serialized as sorted-key compact JSON, UTF-8, sha256.

Usage:
  quote_tool.py normalize <capture.xml>            # print normalized text
  quote_tool.py find <capture.xml> <substring>     # anchor + hash for span
  quote_tool.py span <capture.xml> <start> <end>   # exact span + hash
  quote_tool.py review-hash <page.json>            # interim review digest
  quote_tool.py verify <page.json> <captures-dir>  # recompute all span
                                                   # hashes + source digests
"""
import hashlib
import json
import re
import sys
from xml.etree import ElementTree

REVIEW_EXCLUDED_FIELDS = ("review_payload", "verified", "generated",
                          "source_watch", "status")


def normalized_text(xml_path):
    root = ElementTree.parse(xml_path).getroot()
    raw = "".join(root.itertext())
    return re.sub(r"\s+", " ", raw).strip()


def span_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def review_payload_hash(page):
    core = {k: v for k, v in page.items() if k not in REVIEW_EXCLUDED_FIELDS}
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def file_sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def cmd_find(xml_path, needle):
    text = normalized_text(xml_path)
    idx = text.find(needle)
    if idx < 0:
        print("NOT FOUND", file=sys.stderr)
        sys.exit(1)
    if text.find(needle, idx + 1) >= 0:
        print("WARNING: substring occurs more than once; "
              "first occurrence used", file=sys.stderr)
    end = idx + len(needle)
    print(json.dumps({"anchor": f"normalized:{idx}-{end}",
                      "span": needle, "span_sha256": span_hash(needle)}))


def cmd_verify(page_path, captures_dir):
    import os
    page = json.load(open(page_path))
    capture_files = {}
    for rootdir, _, files in os.walk(captures_dir):
        for fn in files:
            capture_files[fn] = os.path.join(rootdir, fn)
    registry = json.load(
        open(os.path.join(os.path.dirname(captures_dir),
                          "source-registry.dbp-first-proof.json")))
    reg = {s["source_id"]: s for s in registry["sources"]}
    failures = []
    for ref in page["source_refs"]:
        src = reg.get(ref["source_id"])
        if not src:
            failures.append(f"source_ref {ref['source_id']}: not in registry")
            continue
        if src["captured_sha256"] != ref["captured_sha256"]:
            failures.append(f"source_ref {ref['source_id']}: digest mismatch")
        dec = src["reproduction_decision"]
        if dec["status"] != "approved":
            failures.append(f"source_ref {ref['source_id']}: not approved")
        if dec["decision_payload_sha256"] != \
                ref["licensing_decision_payload_sha256"]:
            failures.append(
                f"source_ref {ref['source_id']}: licensing digest mismatch")
    texts = {}
    for q in page["quotes"]:
        sid = q["source_id"]
        unit = sid.rsplit(".", 1)[-1]
        fn = f"section-{unit.replace('-', '.', 1)}.xml" \
            if unit[0].isdigit() else None
        # resolve capture file by matching registry resource section param
        src = reg[sid]
        m = re.search(r"section=([0-9.]+)", src["resource"])
        if m:
            fn = f"section-{m.group(1)}.xml"
        elif "subpart=Q" in src["resource"]:
            fn = "subpart-Q.xml"
        path = capture_files.get(fn)
        if not path:
            failures.append(f"quote {q['quote_id']}: no capture file {fn}")
            continue
        if file_sha256(path) != q["captured_source_sha256"]:
            failures.append(f"quote {q['quote_id']}: capture digest mismatch")
            continue
        if path not in texts:
            texts[path] = normalized_text(path)
        m2 = re.match(r"^normalized:(\d+)-(\d+)$", q["anchor"]["value"])
        if not m2:
            failures.append(f"quote {q['quote_id']}: bad anchor format")
            continue
        span = texts[path][int(m2.group(1)):int(m2.group(2))]
        if span_hash(span) != q["span_sha256"]:
            failures.append(f"quote {q['quote_id']}: span hash mismatch "
                            f"(anchored text: {span[:60]!r})")
    quote_ids = {q["quote_id"] for q in page["quotes"]}
    for c in page["claims"]:
        for qid in c["supporting_quote_ids"]:
            if qid not in quote_ids:
                failures.append(f"claim {c['claim_id']}: unknown quote {qid}")
    if failures:
        print("\n".join("FAIL: " + f for f in failures))
        sys.exit(1)
    print(f"VERIFY OK: {len(page['source_refs'])} source refs, "
          f"{len(page['quotes'])} quotes, {len(page['claims'])} claims")


def main():
    cmd = sys.argv[1]
    if cmd == "normalize":
        print(normalized_text(sys.argv[2]))
    elif cmd == "find":
        cmd_find(sys.argv[2], sys.argv[3])
    elif cmd == "span":
        text = normalized_text(sys.argv[2])
        s, e = int(sys.argv[3]), int(sys.argv[4])
        print(json.dumps({"anchor": f"normalized:{s}-{e}",
                          "span": text[s:e],
                          "span_sha256": span_hash(text[s:e])}))
    elif cmd == "review-hash":
        print(review_payload_hash(json.load(open(sys.argv[2]))))
    elif cmd == "verify":
        cmd_verify(sys.argv[2], sys.argv[3])
    else:
        print(__doc__, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
