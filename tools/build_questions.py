#!/usr/bin/env python3
"""Build evaluation/questions.dbp-v0.1.json from docs/EPA_DBP_Challenge_Questions.md.

The question text and answer key are parsed from the markdown verbatim; this
script never rewrites them. IDs are DBP-Q01..DBP-Q40 in markdown order. Labels,
expected page IDs (from proposals/first-proof-dbp-page-list-v0.2.md), expected
claim IDs (only claims that exist in pages/ today) and expected values (copied
from the answer key) come from the ANNOTATIONS table below, which is CC's
draft for Skitch's confirmation (Charter v1.1, Done item 2).

Usage: build_questions.py [--check]   (--check: fail if the output is stale)
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "EPA_DBP_Challenge_Questions.md"
OUT = ROOT / "evaluation" / "questions.dbp-v0.1.json"

# label: supported | out-of-scope | pending-D1   (reason: why a label was set, e.g. a ruling)
# pages: expected page_ids from page list v0.2 (future pages included)
# claims: expected claim_ids that exist in pages/ today
# values: strings copied from the answer key that a correct answer must contain
# flag: anything needing Skitch's judgment
A = {
 1: dict(label="out-of-scope", reason="EPA guide only, Skitch D1 2026-11-01", pages=[], flag="Purpose statement; EPA guide content, not CFR text."),
 2: dict(label="out-of-scope", reason="EPA guide only, Skitch D1 2026-11-01", pages=[], flag="Health effects; EPA guide content, not CFR text."),
 3: dict(label="supported", pages=["dbp.applicability.stage2"]),
 4: dict(label="supported", pages=["dbp.applicability.stage2"], values=["ultraviolet"]),
 5: dict(label="supported", pages=["dbp.applicability.stage2"], values=["consecutive"]),
 6: dict(label="out-of-scope", reason="EPA guide only, Skitch D1 2026-11-01", pages=[], flag="Federal Register publication dates; history, not operative CFR text."),
 7: dict(label="supported", pages=["dbp.applicability.stage2"], values=["chlorine dioxide"]),
 8: dict(label="supported", pages=["dbp.applicability.stage2"], values=["40 CFR 141"],
         flag="Answer key adds 'plus any approved state requirements', which no federal page can quote. Confirm the federal part alone is a correct answer."),
 9: dict(label="supported", pages=["dbp.mcl.tthm"], values=["0.080"]),
 10: dict(label="supported", pages=["dbp.mcl.haa5"], values=["0.060"]),
 11: dict(label="supported", pages=["dbp.mcl.bromate"], values=["0.010", "ozone"]),
 12: dict(label="supported", pages=["dbp.mclg"], claims=["claim.dbp.mclg.bromate"], values=["zero"]),
 13: dict(label="supported", pages=["dbp.mcl.chlorite", "dbp.mclg"], claims=["claim.dbp.mclg.chlorite"], values=["1.0", "0.8", "chlorine dioxide"]),
 14: dict(label="supported", pages=["dbp.mrdl.chlorine-chloramine", "dbp.mclg"], claims=["claim.dbp.mclg.mrdlg-chlorine", "claim.dbp.mclg.mrdlg-chloramines"], values=["4.0"]),
 15: dict(label="supported", pages=["dbp.mrdl.chlorine-dioxide", "dbp.mclg"], claims=["claim.dbp.mclg.mrdlg-chlorine-dioxide"], values=["0.8"]),
 16: dict(label="out-of-scope", reason="EPA guide only, Skitch D1 2026-11-01", pages=[], flag="Stage 1 vs Stage 2 comparison; history, not operative CFR text."),
 17: dict(label="supported", pages=["dbp.definitions"], claims=["claim.dbp.definitions.tthm-composition"], values=["chloroform", "bromodichloromethane", "dibromochloromethane", "bromoform"]),
 18: dict(label="supported", pages=["dbp.definitions"], claims=["claim.dbp.definitions.haa5-composition"], values=["monochloroacetic acid", "dichloroacetic acid", "trichloroacetic acid", "monobromoacetic acid", "dibromoacetic acid"]),
 19: dict(label="supported", pages=["dbp.compliance.lraa"], values=["running annual average"], flag="Stage 1 RAA still operative for subpart L systems at 141.133(b)(1); confirm page placement."),
 20: dict(label="supported", pages=["dbp.compliance.lraa", "dbp.definitions"], claims=["claim.dbp.definitions.lraa-computation"], values=["locational running annual average"]),
 21: dict(label="supported", pages=["dbp.compliance.lraa"], flag="The 'why' is reasoning, not quotable text; grade the explanation as labeled context."),
 22: dict(label="supported", pages=["dbp.mcl.bromate"], values=["entry point"], flag="'Did Stage 2 change it' is history; grade the compliance-basis half."),
 23: dict(label="supported", pages=["dbp.mcl.chlorite", "dbp.definitions"], claims=["claim.dbp.definitions.chlorite-three-sample-set"], values=["three-sample", "1.0"]),
 24: dict(label="out-of-scope", reason="EPA guide only, Skitch D1 2026-11-01", pages=[], flag="Reconciles two EPA guide statements; guide content, not CFR text."),
 25: dict(label="supported", pages=["dbp.monitoring.routine", "dbp.mcl.bromate"], values=["entry point", "monthly"]),
 26: dict(label="supported", pages=["dbp.monitoring.routine", "dbp.definitions"], claims=["claim.dbp.definitions.chlorite-three-sample-set"], values=["daily", "monthly"]),
 27: dict(label="supported", pages=["dbp.monitoring.routine"], values=["daily"]),
 28: dict(label="supported", pages=["dbp.monitoring.routine"], flag="Answer key says RTCR; CFR 141.132(c)(1) text says total coliform sampling. Confirm wording tolerance."),
 29: dict(label="supported", pages=["dbp.monitoring.routine", "dbp.monitoring.idse"], values=["IDSE"]),
 30: dict(label="supported", pages=["dbp.monitoring.idse"], values=["July 1, 2010"], flag="Confirm the date appears in captured 141.600-605 text at page build; if not, this becomes history."),
 31: dict(label="supported", pages=["dbp.monitoring.routine"], values=["highest"]),
 32: dict(label="supported", pages=["dbp.monitoring.reduced-increased"], values=["0.040", "0.030", "No"]),
 33: dict(label="supported", pages=["dbp.monitoring.reduced-increased"], values=["0.0025"], flag="The pre-April-2009 bromide criterion may no longer be in current CFR text; the bromate criterion half should be."),
 34: dict(label="supported", pages=["dbp.monitoring.reduced-increased", "dbp.precursors.toc"], values=["4.0"]),
 35: dict(label="supported", pages=["dbp.compliance.oel"], values=["Q1", "Q2", "2Q3", "4"]),
 36: dict(label="supported", pages=["dbp.compliance.oel"], values=["90 days"]),
 37: dict(label="supported", pages=["dbp.compliance.oel"], values=["quarterly"]),
 38: dict(label="supported", pages=["dbp.precursors.toc"], values=["35.0", "25.0", "No"], flag="Table-valued claim; answer depends on cell selection."),
 39: dict(label="supported", pages=["dbp.precursors.toc"], values=["enhanced coagulation", "enhanced softening"]),
 40: dict(label="supported", pages=["dbp.applicability.stage2"], values=["April 1, 2012"], flag="Schedule table at 141.620(c); confirm which page carries it."),
}


def parse(md):
    head, key = md.split("\n## Answer Key\n", 1)
    item = re.compile(r"^(\d+)\.\s+(.*?)(?=^\d+\.\s|\Z)", re.S | re.M)
    qs = {int(n): " ".join(t.split()) for n, t in item.findall(head)}
    ks = {int(n): " ".join(t.split()) for n, t in item.findall(key)}
    assert sorted(qs) == list(range(1, 41)), sorted(qs)
    assert sorted(ks) == list(range(1, 41)), sorted(ks)
    return qs, ks


def build():
    md = SRC.read_text(encoding="utf-8")
    qs, ks = parse(md)
    questions = []
    for n in range(1, 41):
        a = A[n]
        questions.append({
            "id": f"DBP-Q{n:02d}",
            "question": qs[n],
            "answer_key": ks[n],
            "label": a["label"],
            "label_reason": a.get("reason"),
            "expected_page_ids": a.get("pages", []),
            "expected_claim_ids": a.get("claims", []),
            "expected_values": a.get("values", []),
            "safety": None,
            "flag": a.get("flag"),
            "confirmed_by_skitch": False,
        })
    return {
        "schema_version": "dbp-question-bank/v0.1-draft",
        "source": {"path": "docs/EPA_DBP_Challenge_Questions.md",
                   "sha256": hashlib.sha256(md.encode("utf-8")).hexdigest()},
        "labels": {"supported": "answerable from the 17-page DBP list",
                   "out-of-scope": "deliberately outside the DBP pages; a decline is correct",
                   "pending-D1": "guide-only question awaiting Skitch's decision D1"},
        "notes": ["Draft by CC 2026-11-01 for Skitch's confirmation; question and answer_key text are verbatim from the markdown.",
                  "expected_page_ids use page IDs from proposals/first-proof-dbp-page-list-v0.2.md; expected_claim_ids only name claims that exist in pages/ today.",
                  "safety is null (unassigned) on every question until Skitch assigns true or false; the bar is not scorable while any is null.",
                  "Conversion to the ratified evaluation-manifest/v0.1 schema is a later step."],
        "questions": questions,
    }


def main():
    doc = build()
    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    if "--check" in sys.argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print("STALE: evaluation/questions.dbp-v0.1.json differs from a fresh build", file=sys.stderr)
            sys.exit(1)
        print("questions.json is current")
        return
    OUT.write_text(text, encoding="utf-8")
    qs = doc["questions"]
    print(f"wrote {OUT.relative_to(ROOT)}: {len(qs)} questions; labels:",
          {l: sum(q['label'] == l for q in qs) for l in doc['labels']},
          f"; {sum(1 for q in qs if q['flag'])} flagged")


if __name__ == "__main__":
    main()
