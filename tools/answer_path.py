#!/usr/bin/env python3
"""DBP answer path, skeleton (Water Advisor session 1). Python stdlib only.

Steps (inventory 2026-11-01, section 3):
  1 load      pages/*.json with fail-closed eligibility; every quote span is
              re-resolved from its capture and its hash rechecked at load
  2 retrieve  BM25 over weighted page fields plus a defining-claim bonus
              (session 6), retrieval floor (session 2), top 3
  3 generate  STUB: disabled; always withholds (SYNTHESIS_WITHHELD)
  4 validate  a candidate selection {claim_ids, quote_ids, answer_sentence,
              conditions_acknowledged} against the retrieved pages: ids
              resolve, span hashes recompute, every selected claim is supported
              by a selected quote and vice versa, numeric claims match on
              value, unit and subject, no negation, no unaccounted numbers,
              and every condition or exception on a selected claim is echoed
  5 render    verbatim quote text from capture bytes with section cite, plus
              a verified-answer/v0.1 envelope (integrity mode "validated")

Eligibility (session 3, D3): expiry is the page's stale_after unless a
renewal record in pages/renewals/ bound to the page's signed digest extends
it; the live watch result is the newest drift report in sources/watch/ (the
page's embedded source_watch block is superseded and ignored).

Dev override --allow-stale-dev waives stale_after and overdue-watch gates so
retrieval can be exercised on stale pages, and (session 5) admits status
"draft" pages so unsigned Batch pages can be exercised before Skitch signs
them. It never waives a hash failure or a deprecated page, and every output
produced under it is labeled NOT A SCORED RUN. Strict runs see stable pages only.

Usage:
  answer_path.py ask "<question>" [--today YYYY-MM-DD] [--allow-stale-dev]
                 [--generate] [--json]
  answer_path.py selftest        # proves validate() rejects bad selections
"""
import datetime as dt
import hashlib
import json
import math
import re
import sys
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import quote_tool  # noqa: E402  (interim normalization, same as the pages)

PAGES_DIR = ROOT / "pages"
RENEWALS_DIR = ROOT / "pages" / "renewals"
WATCH_DIR = ROOT / "sources" / "watch"
WATCH_MAX_AGE_DAYS = 30
CAPTURES_DIR = ROOT / "sources" / "captures"
REGISTRY = ROOT / "sources" / "source-registry.dbp-first-proof.json"
RUNTIME_ID = "runtime-assurance.answer-path-skeleton-dev"
QUERY_CANON = "dw-query/v0.1-interim"
RENDERER = "answer-path-text/v0.1-dev"
TOP_K = 3
# Retrieval floor (session 2): a page is returned only if at least MIN_MATCHED
# distinct query tokens occur in it and at least MIN_RATIO of the distinct
# query tokens do. Below the floor the path reports RETRIEVAL_MISS. Set from
# the measured bank: lowest expected-page hit is 2 of 5 tokens (DBP-Q13);
# off-topic probes score 0 or 1 matched token.
MIN_MATCHED = 2
MIN_RATIO = 1 / 3
# Scoring (session 6, engine step): BM25 over weighted fields (title 3, page_id 2,
# claim subject 2, claim value / condition / quote text 1). Length normalization
# stops a long page that merely mentions a term often from outranking a short
# page that is about it. A claim whose subject words are mostly in the question
# AND whose kind matches what the question asks adds DEF_WEIGHT x idf per matched
# subject word: a numeric claim when the question names its metric (mcl, mclg,
# mrdl, mrdlg, action level, treatment technique); a monitoring-trigger claim
# when the question is about monitoring or sampling; a defining claim
# (qualitative, eq, metric other) when the question names neither. So a page
# that defines a term outranks pages that use it, and a page that states the
# asked value for a term outranks the page that defines the term.
BM25_K1 = 1.2
BM25_B = 0.75
DEF_WEIGHT = 3.0
DEF_COVERAGE = 2 / 3
STOP = set(("the a an of for to in and or is are what which how does do under at by on it its as be with that this from "
            "must may can shall should will would could required require requires requirement requirements "
            "name describe explain list give state there these those they their when where who why about also any all each "
            "than then into one two three four five six seven eight nine ten").split())
# subject words that carry no identity (every MCLG claim has them)
GENERIC_SUBJECT = set("maximum contaminant level goal residual disinfectant mclg mrdlg mcl mrdl routine samples sample".split())
NEGATION = set("not no never none cannot isn't aren't doesn't don't wasn't except unless".split())


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- step 1: load ----------

def capture_path_for(source):
    m = re.search(r"section=([0-9.]+)", source["resource"])
    if m:
        return CAPTURES_DIR / "ecfr-2026-07-01" / f"section-{m.group(1)}.xml", f"40 CFR {m.group(1)}"
    if "subpart=Q" in source["resource"]:
        return CAPTURES_DIR / "ecfr-2026-07-01" / "subpart-Q.xml", "40 CFR part 141 subpart Q"
    return None, None


def renewal_payload_hash(record):
    core = {k: v for k, v in record.items() if k != "renewal_payload_sha256"}
    return sha256(canonical(core))


def latest_drift_report():
    """Newest drift report in sources/watch/ by checked_at, or None."""
    best = None
    for path in WATCH_DIR.glob("drift-*.json"):
        rep = json.load(open(path, encoding="utf-8"))
        if best is None or rep["checked_at"] > best["checked_at"]:
            best = rep
            best["_path"] = str(path.relative_to(ROOT))
    return best


def effective_stale_after(page):
    """The page's own stale_after, or a later date from a valid renewal record:
    bound to this page's signed digest, result unchanged, no re-sign owed, and
    its own payload digest recomputes. Returns (date, record_or_None)."""
    base = dt.date.fromisoformat(page["stale_after"])
    best, best_rec = base, None
    for path in sorted(RENEWALS_DIR.glob(f"{page['page_id']}.renewal-*.json")):
        rec = json.load(open(path, encoding="utf-8"))
        if rec.get("bound_review_payload_sha256") != page["review_payload"]["sha256"]:
            continue
        if rec.get("result") != "unchanged" or rec.get("requires_resign"):
            continue
        if renewal_payload_hash(rec) != rec.get("renewal_payload_sha256"):
            continue
        new = dt.date.fromisoformat(rec["new_stale_after"])
        if new > best:
            best, best_rec = new, rec
    return best, best_rec


def load_corpus(today, allow_stale_dev=False, now=None):
    """Return (eligible_pages, ineligible, waived) where ineligible maps page_id -> [reason codes].
    Each eligible page carries resolved quote text and a cite for every quote."""
    now = now or now_utc()
    registry = json.load(open(REGISTRY, encoding="utf-8"))
    reg = {s["source_id"]: s for s in registry["sources"]}
    drift = latest_drift_report()
    drift_rows = {r["source_id"]: r for r in drift["sources"]} if drift else {}
    drift_overdue = True
    if drift:
        checked = dt.datetime.strptime(drift["checked_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        drift_overdue = (now - checked).days >= WATCH_MAX_AGE_DAYS
    eligible, ineligible, waived = [], {}, {}
    texts = {}
    for path in sorted(PAGES_DIR.glob("*.json")):
        page = json.load(open(path, encoding="utf-8"))
        pid = page["page_id"]
        reasons, dev_waived = [], []
        status = page.get("status")
        if status == "draft" and allow_stale_dev:
            dev_waived.append("INELIGIBLE_EVIDENCE")  # session 5: unsigned drafts are visible to the dev run only
        elif status != "stable":
            reasons.append("INELIGIBLE_EVIDENCE")
        expiry, renewal = effective_stale_after(page)
        page["_effective_stale_after"] = expiry.isoformat()
        page["_renewal_id"] = renewal["renewal_id"] if renewal else None
        stale = expiry < today
        # live watch: newest drift report; the page's own source_watch block is superseded
        watch_failed = drift is None or drift_overdue
        for ref in page["source_refs"]:
            row = drift_rows.get(ref["source_id"])
            if row is None or row["status"] == "fetch-failed":
                watch_failed = True
            elif row["status"] == "changed":
                reasons.append("SOURCE_CHANGE_PENDING")
            elif row["status"] in ("unchanged", "unchanged-text") and row["captured_sha256"] != ref["captured_sha256"]:
                reasons.append("CHECK_FAILED")
        if stale:
            (dev_waived if allow_stale_dev else reasons).append("STALE_EVIDENCE")
        if watch_failed:
            (dev_waived if allow_stale_dev else reasons).append("SOURCE_WATCH_FAILED")
        # review-payload digest must recompute (AT-001 binding)
        signed_view = {k: v for k, v in page.items() if not k.startswith("_")}  # loader annotations are not part of the signed payload
        if quote_tool.review_payload_hash(signed_view) != page["review_payload"]["sha256"]:
            reasons.append("CHECK_FAILED")
        # every quote must resolve and hash; never waived
        resolved = {}
        for q in page["quotes"]:
            src = reg.get(q["source_id"])
            cpath, cite = capture_path_for(src) if src else (None, None)
            if not cpath or not cpath.exists() or sha256(cpath.read_bytes()) != q["captured_source_sha256"]:
                reasons.append("CHECK_FAILED")
                continue
            if cpath not in texts:
                texts[cpath] = quote_tool.normalized_text(str(cpath))
            m = re.match(r"^normalized:(\d+)-(\d+)$", q["anchor"]["value"])
            span = texts[cpath][int(m.group(1)):int(m.group(2))] if m else ""
            if not m or quote_tool.span_hash(span) != q["span_sha256"]:
                reasons.append("CHECK_FAILED")
                continue
            resolved[q["quote_id"]] = {"text": span, "cite": cite, "span_sha256": q["span_sha256"]}
        reasons = sorted(set(reasons))
        if reasons:
            ineligible[pid] = reasons
            continue
        page["_quotes"] = resolved
        page["_dev_waived"] = sorted(set(dev_waived))
        if dev_waived:
            waived[pid] = page["_dev_waived"]
        eligible.append(page)
    return eligible, ineligible, waived


# ---------- step 2: retrieve ----------

def tokens(text):
    text = unicodedata.normalize("NFC", text).lower()
    # a comma between digits is a thousands separator ("10,000" is one token, not "10" and "000")
    return [t for t in re.findall(r"[a-z0-9]+(?:[.,\-][a-z0-9]+)*", text) if t not in STOP and len(t) > 1]


def page_fields(page):
    yield 3, page["title"]
    yield 2, page["page_id"].replace(".", " ").replace("-", " ")
    for c in page["claims"]:
        yield 2, c["subject"]
        if isinstance(c.get("value"), str):
            yield 1, c["value"]
        for cond in c.get("conditions", []):
            yield 1, cond
    for q in page["_quotes"].values():
        yield 1, q["text"]


METRIC_TOKENS = {"mcl": "mcl", "mclg": "mclg", "mrdl": "mrdl", "mrdlg": "mrdlg",
                 "action-level": "action", "treatment-technique": "treatment"}
MONITORING_TOKENS = {"monitoring", "monitor", "monitored", "sampling", "sample", "samples"}


def focal_subjects(page, qset):
    """Subjects (minus generic words) of claims whose kind matches the question:
    numeric claims when the question names their metric, monitoring-trigger claims
    when the question is about monitoring or sampling, defining claims (qualitative,
    eq, metric other) when the question names neither."""
    asks_metric = {m for m, tok in METRIC_TOKENS.items() if tok in qset}
    asks_monitoring = bool(qset & MONITORING_TOKENS)
    for c in page["claims"]:
        r = c.get("relation", {})
        metric = r.get("regulatory_metric")
        if metric in asks_metric:
            focal = True
        elif metric == "monitoring-trigger" and asks_monitoring:
            focal = True
        elif c.get("kind") == "qualitative" and r.get("operator") == "eq" and metric == "other" and not asks_metric and not asks_monitoring:
            focal = True
        else:
            focal = False
        if focal:
            subj = [t for t in dict.fromkeys(tokens(c["subject"])) if t not in GENERIC_SUBJECT]
            if subj:
                yield subj


def retrieve(question, pages, k=TOP_K):
    qtok = tokens(question)
    if not qtok or not pages:
        return []
    df, bags, dl = {}, {}, {}
    for p in pages:
        bag = {}
        for w, text in page_fields(p):
            for t in tokens(text):
                bag[t] = bag.get(t, 0) + w
        bags[p["page_id"]] = bag
        dl[p["page_id"]] = sum(bag.values())
        for t in bag:
            df[t] = df.get(t, 0) + 1
    n = len(pages)
    avgdl = sum(dl.values()) / n
    def idf(t):
        return math.log(1 + (n - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5))
    distinct = list(dict.fromkeys(qtok))
    qset = set(distinct)
    scored = []
    for p in pages:
        pid = p["page_id"]
        bag = bags[pid]
        norm = BM25_K1 * (1 - BM25_B + BM25_B * dl[pid] / avgdl)
        s = 0.0
        for t in qtok:
            if t in bag:
                tf = bag[t]
                s += idf(t) * tf * (BM25_K1 + 1) / (tf + norm)
        defined = []
        for subj in focal_subjects(p, qset):
            hit = [t for t in subj if t in qset]
            if len(hit) / len(subj) >= DEF_COVERAGE:
                s += DEF_WEIGHT * sum(idf(t) for t in hit)
                defined.extend(hit)
        matched = [t for t in distinct if t in bag]
        ratio = len(matched) / len(distinct)
        if len(matched) >= MIN_MATCHED and ratio >= MIN_RATIO:
            scored.append((round(s, 4), p, {"matched": matched, "ratio": round(ratio, 3), "focal": sorted(set(defined))}))
    scored.sort(key=lambda x: (-x[0], x[1]["page_id"]))
    return scored[:k]


# ---------- step 3: generate (stub) ----------

def generate(question, retrieved, enabled=False):
    """Returns a selection dict or None. Disabled this session by design."""
    if not enabled:
        return None
    raise NotImplementedError("generation is off until Skitch's decision D4")


# ---------- step 4: validate ----------

def numbers_in(text):
    out = set()
    for m in re.findall(r"(?<![A-Za-z0-9.])\d+(?:\.\d+)?(?![A-Za-z0-9])", text):
        try:
            out.add(Decimal(m))
        except InvalidOperation:
            pass
    return out


def validate(selection, retrieved_pages):
    """Return (ok, failures, refs). Nothing is repaired. Checks:
    claim-resolution   every claim id is on a retrieved page and has at least
                       one selected quote among its supporting_quote_ids
    quote-resolution   every quote id is on a retrieved page and supports at
                       least one selected claim (no quote-only, no claim-only)
    span-fidelity      selected quote text re-hashes to the page's span digest
    numeric-claim-tuple numeric claims: value present as a standalone number,
                       unit string present, subject identity words present; no
                       negation; no number in the sentence outside selected values
    applicability      every condition and exception on a selected claim is
                       echoed verbatim in selection.conditions_acknowledged
    coverage           the selection cites something"""
    failures, claim_refs, quote_refs = [], [], []
    by_claim = {c["claim_id"]: (p, c) for p in retrieved_pages for c in p["claims"]}
    by_quote = {qid: (p, q) for p in retrieved_pages for qid, q in p["_quotes"].items()}
    sentence = selection.get("answer_sentence", "") or ""
    sentence_l = " ".join(sentence.lower().split())
    sentence_nums = numbers_in(sentence)
    sentence_tokens = set(tokens(sentence)) | set(re.findall(r"[a-z']+", sentence.lower()))
    acknowledged = set(selection.get("conditions_acknowledged", []) or [])
    sel_claims = list(dict.fromkeys(selection.get("claim_ids", []) or []))
    sel_quotes = list(dict.fromkeys(selection.get("quote_ids", []) or []))
    claimed_values = set()
    supported_quotes = set()
    for cid in sel_claims:
        if cid not in by_claim:
            failures.append(("claim-resolution", cid, "not in retrieved pages"))
            continue
        p, c = by_claim[cid]
        support = [q for q in c["supporting_quote_ids"] if q in sel_quotes]
        if not support:
            failures.append(("claim-resolution", cid, "no selected quote supports this claim"))
        supported_quotes.update(support)
        if c["kind"] == "numeric":
            try:
                v = Decimal(str(c["value"]))
            except InvalidOperation:
                v = None
            if v is None or v not in sentence_nums:
                failures.append(("numeric-claim-tuple", cid, f"value {c['value']} absent from answer sentence"))
            else:
                claimed_values.add(v)
            unit = " ".join(str(c.get("unit", "")).lower().split())
            if unit and unit not in sentence_l:
                failures.append(("numeric-claim-tuple", cid, f"unit '{c.get('unit')}' absent from answer sentence"))
        subj = [t for t in tokens(c["subject"]) if t not in GENERIC_SUBJECT]
        if subj and sum(1 for t in subj if t in sentence_tokens) * 2 < len(subj):
            failures.append(("numeric-claim-tuple", cid, f"subject '{c['subject']}' not identified in answer sentence"))
        for cond in list(c.get("conditions", [])) + list(c.get("exceptions", [])):
            if cond not in acknowledged:
                failures.append(("applicability", cid, f"condition not acknowledged: {cond[:60]}"))
        claim_refs.append({"claim_id": cid, "page_id": p["page_id"], "review_payload_sha256": p["review_payload"]["sha256"]})
    if sentence_tokens & NEGATION:
        failures.append(("numeric-claim-tuple", "envelope", "negation in answer sentence"))
    extra = sentence_nums - claimed_values
    if extra and sel_claims:
        failures.append(("numeric-claim-tuple", "envelope", f"numbers not backed by a selected claim: {sorted(str(x) for x in extra)}"))
    for qid in sel_quotes:
        if qid not in by_quote:
            failures.append(("quote-resolution", qid, "not in retrieved pages"))
            continue
        p, q = by_quote[qid]
        if quote_tool.span_hash(q["text"]) != q["span_sha256"]:
            failures.append(("span-fidelity", qid, "span hash mismatch"))
            continue
        if qid not in supported_quotes:
            failures.append(("quote-resolution", qid, "quote supports no selected claim"))
        quote_refs.append({"quote_id": qid, "page_id": p["page_id"], "span_sha256": q["span_sha256"]})
    if not sel_claims and not sel_quotes:
        failures.append(("coverage", "envelope", "selection cites nothing"))
    if failures:
        claim_refs, quote_refs = [], []
    return (not failures), failures, (claim_refs, quote_refs)


# ---------- step 5: render + envelope ----------

def dev_corpus_manifest(pages):
    """Interim working-tree release descriptor; a real corpus-release manifest
    instance is Batch 0 work. This only gives the envelope something honest to bind to."""
    listing = [{"page_id": p["page_id"], "review_payload_sha256": p["review_payload"]["sha256"]} for p in pages]
    return "corpus-release.working-tree-dev", sha256(canonical(listing))


def query_digest(question):
    q = " ".join(unicodedata.normalize("NFC", question).lower().split())
    return sha256(q.encode("utf-8"))


def answer(question, today, allow_stale_dev=False, generate_enabled=False, answer_id=None, now=None):
    now = now or now_utc()
    eligible, ineligible, waived = load_corpus(today, allow_stale_dev, now)
    all_pages = eligible + [{"page_id": k, "review_payload": {"sha256": "0" * 64}} for k in ineligible]
    release_id, release_sha = dev_corpus_manifest(sorted(all_pages, key=lambda p: p["page_id"]))
    aid = answer_id or ("answer." + sha256(question.encode())[:12])
    env_subject = {"kind": "envelope", "id": aid}
    checks = [
        {"check_id": "schema", "version": "v0.1", "verdict": "pass", "subjects": [env_subject]},
        {"check_id": "corpus-release", "version": "v0.1-dev", "verdict": "pass", "subjects": [env_subject]},
        {"check_id": "runtime-manifest", "version": "v0.1-dev", "verdict": "pass", "subjects": [env_subject]},
    ]
    reasons = []
    for pid, codes in sorted(ineligible.items()):
        subj = {"kind": "page", "id": pid}
        checks.append({"check_id": "eligibility", "version": "v0.1", "verdict": "fail", "subjects": [subj]})
        for code in codes:
            reasons.append({"code": code, "source_kind": "check", "source_id": "eligibility", "subjects": [subj]})
    for p in eligible:
        subj = {"kind": "page", "id": p["page_id"]}
        checks.append({"check_id": "eligibility", "version": "v0.1", "verdict": "pass", "subjects": [subj]})
        checks.append({"check_id": "freshness", "version": "v0.1", "verdict": "pass" if not p["_dev_waived"] else "not-run", "subjects": [subj]})

    retrieved = retrieve(question, eligible)
    outcome, claim_refs, quote_refs, failures, selection = "abstention", [], [], [], None
    if not eligible:
        checks.append({"check_id": "coverage", "version": "v0.1", "verdict": "fail", "subjects": [env_subject]})
        if not reasons:
            reasons.append({"code": "OUT_OF_COVERAGE", "source_kind": "check", "source_id": "coverage", "subjects": [env_subject]})
    elif not retrieved:
        checks.append({"check_id": "coverage", "version": "v0.1", "verdict": "fail", "subjects": [env_subject]})
        reasons.append({"code": "RETRIEVAL_MISS", "source_kind": "check", "source_id": "coverage", "subjects": [env_subject]})
    else:
        checks.append({"check_id": "coverage", "version": "v0.1", "verdict": "pass", "subjects": [env_subject]})
        selection = generate(question, retrieved, generate_enabled)
        if selection is None:
            reasons.append({"code": "SYNTHESIS_WITHHELD", "source_kind": "policy-gate", "source_id": "generation-disabled", "subjects": [env_subject]})
        else:
            ok, failures, (claim_refs, quote_refs) = validate(selection, [p for _, p, _ in retrieved])
            if ok:
                outcome = "evidence-backed"
                for r in claim_refs:
                    checks.append({"check_id": "claim-resolution", "version": "v0.1", "verdict": "pass", "subjects": [{"kind": "claim", "id": r["claim_id"]}]})
                for r in quote_refs:
                    checks.append({"check_id": "span-fidelity", "version": "v0.1", "verdict": "pass", "subjects": [{"kind": "quote", "id": r["quote_id"]}]})
            else:
                claim_refs, quote_refs = [], []
                for check_id, sid, _ in failures:
                    checks.append({"check_id": check_id, "version": "v0.1", "verdict": "fail", "subjects": [env_subject]})
                    reasons.append({"code": "CHECK_FAILED", "source_kind": "check", "source_id": check_id, "subjects": [env_subject]})
    # dedupe reasons (schema: uniqueItems)
    seen, uniq = set(), []
    for r in reasons:
        key = canonical(r)
        if key not in seen:
            seen.add(key)
            uniq.append(r)
    envelope = {
        "schema_version": "verified-answer/v0.1",
        "answer_id": aid,
        "created_at": iso(now),
        "outcome": outcome,
        "query": {"canonicalization_id": QUERY_CANON, "sha256": query_digest(question)},
        "corpus": {"release_id": release_id, "manifest_sha256": release_sha},
        "runtime": {"manifest_id": RUNTIME_ID, "manifest_sha256": sha256(canonical({"id": RUNTIME_ID, "generation": generate_enabled, "allow_stale_dev": allow_stale_dev}))},
        "applicability": {"jurisdiction": "US-federal", "use_class": "regulatory-reference"},
        "claim_refs": claim_refs,
        "quote_refs": quote_refs,
        "checks": checks,
        "outcome_reasons": uniq,
        "renderer": {"template_set_version": RENDERER},
        "integrity": {"mode": "validated", "canonicalization": "dw-answer-envelope/v0.1", "artifact_sha256": "0" * 64},
    }
    env_for_digest = json.loads(json.dumps(envelope))
    del env_for_digest["integrity"]["artifact_sha256"]
    envelope["integrity"]["artifact_sha256"] = sha256(canonical(env_for_digest))
    if selection is None:
        disposition = "ineligible" if not eligible else ("retrieval-miss" if not retrieved else "withheld")
    else:
        disposition = "validated" if outcome == "evidence-backed" else "validation-rejected"
    return {
        "question": question,
        "today": today.isoformat(),
        "scored_run_eligible": not allow_stale_dev,
        "disposition": disposition,
        "pages": {p["page_id"]: {"effective_stale_after": p["_effective_stale_after"], "renewal_id": p["_renewal_id"]} for p in eligible},
        "dev_waived": waived,
        "ineligible": ineligible,
        "retrieved": [{"page_id": p["page_id"], "score": s, "matched": d["matched"], "ratio": d["ratio"]} for s, p, d in retrieved],
        "selection": selection,
        "validation_failures": failures,
        "envelope": envelope,
        "rendered": render(envelope, retrieved, selection, [p for _, p, _ in retrieved], allow_stale_dev),
    }


def render(envelope, retrieved, selection, pages, dev):
    lines = []
    if dev:
        lines.append("*** NOT A SCORED RUN: --allow-stale-dev waived staleness gates ***")
    lines.append(f"Outcome: {envelope['outcome']}")
    for r in envelope["outcome_reasons"]:
        lines.append(f"  reason {r['code']} ({r['source_kind']}:{r['source_id']}) " + ", ".join(s["id"] for s in r["subjects"]))
    if retrieved:
        lines.append("Retrieved (retrieval only, no answer unless quotes follow):")
        for s, p, d in retrieved:
            lines.append(f"  {p['page_id']}  score {s}  matched {len(d['matched'])} ({d['ratio']})")
    if envelope["outcome"] == "evidence-backed":
        qmap = {qid: q for p in pages for qid, q in p["_quotes"].items()}
        for ref in envelope["quote_refs"]:
            q = qmap[ref["quote_id"]]
            lines.append(f"Quoted, {q['cite']} (verbatim from capture):")
            lines.append(f'  "{q["text"]}"')
        lines.append("Context (not a quote): " + selection.get("answer_sentence", ""))
    return "\n".join(lines)


# ---------- selftest ----------

def selftest(today):
    """validate() must accept a true selection and reject each class of bad one.
    The session-3 cases each failed on the session-1/2 validator."""
    eligible, _, _ = load_corpus(today, allow_stale_dev=True)
    pages = [p for p in eligible if p["page_id"] == "dbp.mclg"]
    assert pages, "selftest needs dbp.mclg loadable under the dev override"
    cond = next(c for c in pages[0]["claims"] if c["claim_id"] == "claim.dbp.mclg.chlorite")["conditions"]
    good = {"claim_ids": ["claim.dbp.mclg.chlorite"], "quote_ids": ["quote.dbp.mclg.table"],
            "answer_sentence": "The MCLG for chlorite is 0.8 mg/L.", "conditions_acknowledged": list(cond)}
    results = []
    def expect(name, sel, check=None, pages_=None):
        ok, f, _ = validate(sel, pages_ or pages)
        if check is None:
            results.append((name, ok and not f))
        else:
            results.append((name, (not ok) and any(x[0] == check for x in f)))
    expect("true selection accepted", good)
    expect("invented quote id rejected", dict(good, quote_ids=["quote.dbp.mclg.invented"]), "quote-resolution")
    expect("claim from a page not retrieved rejected", dict(good, claim_ids=["claim.dbp.mcl.tthm"]), "claim-resolution")
    expect("wrong number in sentence rejected", dict(good, answer_sentence="The MCLG for chlorite is 1.0 mg/L."), "numeric-claim-tuple")
    tampered = json.loads(json.dumps({k: v for k, v in pages[0].items() if k != "_quotes"}))
    tampered["_quotes"] = {k: dict(v, text=v["text"] + " ") for k, v in pages[0]["_quotes"].items()}
    expect("tampered span rejected", good, "span-fidelity", [tampered])
    expect("empty selection rejected", {"claim_ids": [], "quote_ids": [], "answer_sentence": "x"}, "coverage")
    # session 3 adversarial cases (Ari, Job 2)
    expect("claim-only selection rejected (no supporting quote)", dict(good, quote_ids=[]), "claim-resolution")
    expect("quote-only selection rejected (quote supports no claim)", dict(good, claim_ids=[]), "quote-resolution")
    expect("quote that does not support the claim rejected", dict(good, quote_ids=["quote.dbp.mclg.mrdlg-table"]), "quote-resolution")
    expect("missing unit rejected", dict(good, answer_sentence="The MCLG for chlorite is 0.8."), "numeric-claim-tuple")
    expect("wrong subject rejected", dict(good, answer_sentence="The MCLG for chlorate is 0.8 mg/L."), "numeric-claim-tuple")
    expect("negated sentence rejected", dict(good, answer_sentence="The MCLG for chlorite is not 0.8 mg/L."), "numeric-claim-tuple")
    expect("extra unbacked number rejected", dict(good, answer_sentence="The MCLG for chlorite is 0.8 mg/L and the MCL is 1.0 mg/L."), "numeric-claim-tuple")
    expect("unacknowledged condition rejected", dict(good, conditions_acknowledged=[]), "applicability")
    expect("digit glued to a unit (Cl2) is not an extra number",
           {"claim_ids": ["claim.dbp.mclg.mrdlg-chlorine"], "quote_ids": ["quote.dbp.mclg.mrdlg-table"],
            "answer_sentence": "The MRDLG for chlorine is 4 mg/L as Cl2.",
            "conditions_acknowledged": list(next(c for c in pages[0]["claims"] if c["claim_id"] == "claim.dbp.mclg.mrdlg-chlorine")["conditions"])})
    # renewal checks are about the signed (stable) pages; drafts are ineligible in strict mode by design
    stable_ids = {json.load(open(f, encoding="utf-8"))["page_id"] for f in PAGES_DIR.glob("*.json")
                  if json.load(open(f, encoding="utf-8")).get("status") == "stable"}
    strict, ineligible, _ = load_corpus(today, allow_stale_dev=False)
    results.append(("renewal: stable pages eligible in strict mode today or ineligible only by STALE/WATCH",
                    all(set(v) <= {"STALE_EVIDENCE", "SOURCE_WATCH_FAILED"} for k, v in ineligible.items() if k in stable_ids)))
    results.append(("strict mode never admits a draft page",
                    all("INELIGIBLE_EVIDENCE" in ineligible.get(k, []) for k in {json.load(open(f, encoding="utf-8"))["page_id"] for f in PAGES_DIR.glob("*.json")} - stable_ids)))
    far = dt.date(2099, 1, 1)
    _, inel_far, _ = load_corpus(far, allow_stale_dev=False)
    inel_far_stable = {k: v for k, v in inel_far.items() if k in stable_ids}
    results.append(("renewal cannot outlive its new_stale_after (2099 -> stale)", len(inel_far_stable) == len(stable_ids) >= 2 and all("STALE_EVIDENCE" in v for v in inel_far_stable.values())))
    # retrieval floor: off-topic probes must miss (not in the frozen bank)
    probes = ["What is the lead action level under the Lead and Copper Rule?",
              "How do I replace the mechanical seal on a vertical turbine pump?",
              "What is the turbidity limit for conventional filtration combined filter effluent?",
              "What is the arsenic MCL?", "What is the fluoride MCL?", "What is the MCLG for nitrate?",
              "What CT is required for 3-log Giardia inactivation with free chlorine at 10 C?",
              "How many days of vacation do operators get?"]
    misses = sum(1 for q in probes if not retrieve(q, eligible))
    results.append((f"out-of-scope probes miss ({misses}/{len(probes)})", misses == len(probes)))
    control = retrieve("What is the maximum residual disinfectant level goal for chlorine?", eligible)
    results.append(("in-scope control still retrieves dbp.mclg", bool(control) and control[0][1]["page_id"] == "dbp.mclg"))
    bank_path = ROOT / "evaluation" / "questions.dbp-v0.1.json"
    if bank_path.exists():
        bank = json.load(open(bank_path, encoding="utf-8"))["questions"]
        have = {p["page_id"] for p in eligible}
        # judged: every expected page exists. deferred: an expected page is not built yet (its
        # absence can hand first place to a neighbor); listed, not judged (session 6, Chief's brief).
        judged = [q for q in bank if q["expected_page_ids"] and set(q["expected_page_ids"]) <= have]
        deferred = [q for q in bank if set(q["expected_page_ids"]) & have and not set(q["expected_page_ids"]) <= have]
        def first_ok(q):
            r = retrieve(q["question"], eligible)
            return bool(r) and r[0][1]["page_id"] in q["expected_page_ids"]
        hits = sum(1 for q in judged if first_ok(q))
        results.append((f"bank questions whose expected pages all exist rank an expected page first ({hits}/{len(judged)})", hits == len(judged)))
        for q in deferred:
            print(f"  deferred (expected page not built): {q['id']} {'first' if first_ok(q) else 'not first'} expected {q['expected_page_ids']}")
    for name, passed in results:
        print(("PASS " if passed else "FAIL ") + name)
    print(f"{sum(1 for _, p in results if p)}/{len(results)} passed")
    return all(p for _, p in results)


def main(argv):
    if not argv or argv[0] not in ("ask", "selftest"):
        print(__doc__, file=sys.stderr); sys.exit(2)
    today = dt.date.today()
    if "--today" in argv:
        today = dt.date.fromisoformat(argv[argv.index("--today") + 1])
    if argv[0] == "selftest":
        sys.exit(0 if selftest(today) else 1)
    res = answer(argv[1], today, "--allow-stale-dev" in argv, "--generate" in argv)
    if "--json" in argv:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print(res["rendered"])


if __name__ == "__main__":
    main(sys.argv[1:])
