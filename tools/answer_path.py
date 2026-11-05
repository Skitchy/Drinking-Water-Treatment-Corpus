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
NEGATION = set("not no never none cannot isn't aren't doesn't don't wasn't except unless non nonzero".split())  # "non-zero" tokenizes to non + zero (Ari 601)


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
# The regulatory metrics a question can name, by full name (longest first within a family, so "goal" is read before
# the bare level) and by abbreviation (Ari 603: the abbreviations alone let "maximum residual disinfectant level for
# bromate" through as a question about nothing in particular).
METRIC_PHRASES = [("mrdlg", "maximum residual disinfectant level goal"), ("mrdl", "maximum residual disinfectant level"),
                  ("mclg", "maximum contaminant level goal"), ("mcl", "maximum contaminant level"),
                  ("action-level", "action level"), ("treatment-technique", "treatment technique")]


def asked_metrics(question):
    text = " ".join(unicodedata.normalize("NFC", question).lower().split())
    asked = set()
    for metric, phrase in METRIC_PHRASES:
        if phrase in text:
            asked.add(metric); text = text.replace(phrase, " ")
    qset = set(tokens(question))
    return asked | {m for m, tok in METRIC_TOKENS.items() if tok in qset and m in ("mcl", "mclg", "mrdl", "mrdlg")}


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
        # A question that names a regulatory metric (MCL, MCLG, MRDL, MRDLG, action level, treatment technique) is
        # not answered by a page that carries no claim in that metric unless the page matches two further terms
        # beyond the metric words and the generic words. Added 2026-11-05 (Batch 2): the chlorine dioxide MRDL page
        # says "corrective action" and "level" in its quotes, which was enough for "lead action level" to retrieve it.
        asks = asked_metrics(question)
        if asks and not any(c.get("relation", {}).get("regulatory_metric") in asks for c in p["claims"]):
            metric_words = {tok for m, tok in METRIC_TOKENS.items() if m in asks} | {w for m, phrase in METRIC_PHRASES if m in asks for w in phrase.split()}
            if len([t for t in matched if t not in metric_words and t not in GENERIC_SUBJECT]) < MIN_MATCHED:
                continue
        if len(matched) >= MIN_MATCHED and ratio >= MIN_RATIO:
            scored.append((round(s, 4), p, {"matched": matched, "ratio": round(ratio, 3), "focal": sorted(set(defined))}))
    scored.sort(key=lambda x: (-x[0], x[1]["page_id"]))
    return scored[:k]


# ---------- step 3: generate (quote or decline) ----------
# D4 (Skitch 571 and 581, 2026-11-05): the generation step quotes or declines. This generator is a template over
# the retrieved pages' own fields and no model: it picks the claims whose subject and value cover the question,
# writes one clause per claim from the claim's subject, value and unit (the number spelled as the supporting quote
# spells it), acknowledges every condition and exception verbatim, cites every supporting quote, and hands the
# selection to validate(). A selection that validate() rejects is never returned: the generator drops the weakest
# claim and tries again, and declines (None) when nothing validates. So by construction nothing it returns is
# fabricated, rejected or a failed quote; coverage is what the measured run shows. D4's swap rule applies: a
# different generator (a model, another template) is a different GENERATOR id and needs a fresh scored run.
GENERATOR = "quote-or-decline/v0.1"
GEN_MAX_CLAIMS = 3
GEN_MIN_COVERAGE = 1 / 2   # of the question's non-generic tokens, covered by the claim's subject and value
# A value question ("What is the MCL for bromate, and which plants does it apply to?") is answered by the named
# metric's own claim when that claim's subject is at least half about the question, even if the question's other
# words (plants, apply) are not on the claim: the value is the answer the question asks for.
GEN_METRIC_COVERAGE = 1 / 3
GEN_METRIC_PRECISION = 1 / 2
# A question that asks how something is calculated or determined wants the claim that covers it, not the value claim
# in the metric it happens to name; a plain value question ("What is the MRDL for chlorine?") wants the metric's claim
# before any claim that merely mentions the same words.
HOW_TOKENS = {"calculated", "calculate", "computed", "compute", "determined", "determine", "basis",
              "violation", "violations", "exceedance", "exceeded", "exceeds", "corrective"}   # a question about a violation or what follows one is not a value question (Ari 614)


def display_value(value, quote_texts):
    """The value as the source spells it (the page stores 0.080 as the JSON number 0.08); the JSON spelling when
    no supporting quote spells that number."""
    try:
        v = Decimal(str(value))
    except InvalidOperation:
        return str(value)
    if v == 0 and any(re.search(r"\bzero\b", t, re.IGNORECASE) for t in quote_texts):
        return "zero"
    for text in quote_texts:
        for m in re.findall(r"(?<![A-Za-z0-9.])\d+(?:\.\d+)?(?![A-Za-z0-9])", text):
            try:
                if Decimal(m) == v:
                    return m
            except InvalidOperation:
                pass
    return str(value)


def candidate_claims(question, retrieved):
    """Claims on the retrieved pages ranked by: whether the claim's metric is one a value question names, then the
    share of the question's non-generic tokens found in the claim's subject and value, then the share of the claim's
    own subject words that the question uses, then the page's rank."""
    qn = [t for t in dict.fromkeys(tokens(question)) if t not in GENERIC_SUBJECT]
    qset = set(tokens(question))
    asks_metric = asked_metrics(question)
    value_question = not (qset & HOW_TOKENS)
    if not qn:
        return [], asks_metric
    out = []
    for rank, (_, page, _) in enumerate(retrieved):
        if page.get("status") != "stable":
            continue   # generation reads signed pages only (Skitch 571; Ari 602), whatever retrieval was allowed to inspect
        for c in page["claims"]:
            # A value question that names a metric is answered by that metric's claims or not at all (Ari 603): no
            # fall-through to the nearest claim in another metric or in monitoring.
            if value_question and asks_metric and c.get("relation", {}).get("regulatory_metric") not in asks_metric:
                continue
            ctext = c["subject"] + " " + (c["value"] if isinstance(c.get("value"), str) else "")
            ctok = set(tokens(ctext))
            covered = [t for t in qn if t in ctok]
            if not covered:
                continue
            metric = c.get("relation", {}).get("regulatory_metric")
            metric_match = 1 if (value_question and metric in asks_metric) else 0
            subj = [t for t in dict.fromkeys(tokens(c["subject"])) if t not in GENERIC_SUBJECT]
            if subj and not any(t in qset for t in subj):
                continue   # the claim must be about something the question names; words in its value alone do not make it an answer (the turbidity probe)
            precision = (sum(1 for t in subj if t in qset) / len(subj)) if subj else 0.0
            coverage = len(covered) / len(qn)
            if coverage < GEN_MIN_COVERAGE and not (metric_match and coverage >= GEN_METRIC_COVERAGE and precision >= GEN_METRIC_PRECISION):
                continue
            out.append({"page": page, "claim": c, "covered": set(covered), "metric": metric,
                        "key": (metric_match, len(covered) / len(qn), precision, -rank, 1 if c["kind"] == "numeric" else 0)})
    out.sort(key=lambda x: (x["key"], x["claim"]["claim_id"]), reverse=True)
    return out, asks_metric


def compose(selected):
    """One clause per claim from the claim's own words; numbers only from numeric claims' values."""
    numeric_values = set()
    for item in selected:
        c = item["claim"]
        if c["kind"] == "numeric":
            try:
                numeric_values.add(Decimal(str(c["value"])))
            except InvalidOperation:
                pass
    clauses, quote_ids, acknowledged = [], [], []
    for item in selected:
        c, page = item["claim"], item["page"]
        quotes = [page["_quotes"][q]["text"] for q in c["supporting_quote_ids"] if q in page["_quotes"]]
        if c["kind"] == "numeric":
            clause = f"{c['subject']}: {display_value(c['value'], quotes)}" + (f" {c['unit']}" if c.get("unit") else "")
        elif isinstance(c.get("value"), str) and numbers_in(c["value"]) <= numeric_values:
            clause = f"{c['subject']}: {c['value']}"
        else:
            clause = f"{c['subject']} (the quoted text states it)"
        clauses.append(clause.rstrip(".") + ".")
        for q in c["supporting_quote_ids"]:
            if q not in quote_ids:
                quote_ids.append(q)
        for cond in list(c.get("conditions", [])) + list(c.get("exceptions", [])):
            if cond not in acknowledged:
                acknowledged.append(cond)
    return {"claim_ids": [i["claim"]["claim_id"] for i in selected], "quote_ids": quote_ids,
            "answer_sentence": " ".join(clauses), "conditions_acknowledged": acknowledged, "generator": GENERATOR}


def generate(question, retrieved, enabled=False):
    """Returns a selection dict that validate() accepts, or None (decline)."""
    if not enabled or not retrieved:
        return None
    cands, asks_metric = candidate_claims(question, retrieved)
    if not cands:
        return None
    pages = [p for _, p, _ in retrieved if p.get("status") == "stable"]
    best = cands[0]
    selected, covered, metrics = [best], set(best["covered"]), {best["metric"]}
    for item in cands[1:]:
        if len(selected) >= GEN_MAX_CLAIMS:
            break
        same_strength = item["key"][:2] == best["key"][:2]
        new_token = bool(item["covered"] - covered)
        new_asked_metric = item["metric"] in asks_metric and item["metric"] not in metrics
        if same_strength and (new_token or new_asked_metric):
            selected.append(item); covered |= item["covered"]; metrics.add(item["metric"])
    while selected:
        selection = compose(selected)
        ok, _, _ = validate(selection, pages)
        if ok:
            return selection
        selected = selected[:-1]
    return None


# ---------- step 4: validate ----------

def numbers_in(text):
    out = set()
    # The MCLG table spells the value "zero", so the standalone word counts as the number 0: not "non-zero" or
    # "nonzero" (with any hyphen or dash, Unicode ones included), not "zero point eight", not "zero" glued to a digit
    # (Ari 601 and 606). Every other spoken form of a number is no number at all, which fails a numeric claim.
    plain = re.sub(r"[\u2010-\u2015\u2212\u00ad-]", "-", unicodedata.normalize("NFKC", text)).lower()
    if re.search(r"(?<![a-z0-9-])(?<!non-)(?<!non )zero(?![a-z0-9-])(?!\s*point\b)(?!\s*\d)", plain):   # digits bound it too (Ari 614: "1zero")
        out.add(Decimal(0))
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
        if selection is None and not generate_enabled:
            reasons.append({"code": "SYNTHESIS_WITHHELD", "source_kind": "policy-gate", "source_id": "generation-disabled", "subjects": [env_subject]})
        elif selection is None:
            # the generator ran and found no selection it could stand behind (Ari 604: not the disabled gate)
            reasons.append({"code": "INSUFFICIENT_EVIDENCE", "source_kind": "policy-gate", "source_id": "quote-or-decline", "subjects": [env_subject]})
        else:
            ok, failures, (claim_refs, quote_refs) = validate(selection, [p for _, p, _ in retrieved])
            if ok:
                # The envelope describes this answer (found by the first generated answers, 2026-11-05): it carries the
                # envelope-level checks and the cited pages' checks; another page's failed eligibility is the run's
                # business, not this answer's, and the schema makes every check in an evidence-backed envelope pass.
                # A cited page whose gate was waived by the dev override makes the answer evidence-only, with the
                # waived gate named as the reason; a scored run never waives, so it never produces this outcome.
                cited = {r["page_id"] for r in claim_refs} | {r["page_id"] for r in quote_refs}
                by_id = {p["page_id"]: p for p in eligible}
                checks = [c for c in checks if c["subjects"][0]["kind"] != "page" or c["subjects"][0]["id"] in cited]
                reasons = []
                waived_cited = {pid: by_id[pid]["_dev_waived"] for pid in sorted(cited) if by_id[pid]["_dev_waived"]}
                outcome = "evidence-only" if waived_cited else "evidence-backed"
                for pid, codes in waived_cited.items():
                    for code in codes:
                        reasons.append({"code": code, "source_kind": "policy-gate", "source_id": "dev-override", "subjects": [{"kind": "page", "id": pid}]})
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
        "runtime": {"manifest_id": RUNTIME_ID, "manifest_sha256": sha256(canonical({"id": RUNTIME_ID, "generation": generate_enabled, "generator": GENERATOR if generate_enabled else None, "allow_stale_dev": allow_stale_dev}))},
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
        disposition = "ineligible" if not eligible else ("retrieval-miss" if not retrieved else ("declined" if generate_enabled else "withheld"))
    else:
        disposition = "validated" if outcome in ("evidence-backed", "evidence-only") else "validation-rejected"
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
    if envelope["outcome"] in ("evidence-backed", "evidence-only"):
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
    # the gate that answers: with generation on, every off-topic probe declines end to end, retrieved or not
    declines = sum(1 for q in probes if generate(q, retrieve(q, eligible), True) is None)
    results.append((f"generate: out-of-scope probes decline end to end ({declines}/{len(probes)})", declines == len(probes)))
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
        # D4 property over the whole bank: whatever the generator returns, validate() accepts; a decline is None
        bad = []
        for q in bank:
            r = retrieve(q["question"], eligible)
            sel = generate(q["question"], r, True)
            if sel is not None and not validate(sel, [p for _, p, _ in r])[0]:
                bad.append(q["id"])
        results.append((f"generate: every bank selection validates or is a decline ({len(bank) - len(bad)}/{len(bank)})", not bad))
    # D4 generation (quote or decline): named cases
    def gen(q):
        r = retrieve(q, eligible)
        return generate(q, r, True), [p for _, p, _ in r]
    sel, pages_ = gen("What is the MCLG for chlorite?")
    results.append(("generate: MCLG for chlorite quotes claim.dbp.mclg.chlorite and validates", sel is not None and sel["claim_ids"] == ["claim.dbp.mclg.chlorite"] and validate(sel, pages_)[0]))
    sel, _ = gen("What is the MCL for Total Trihalomethanes (TTHM)?")
    results.append(("generate: the TTHM MCL is spelled as the source spells it (0.080 mg/L)", sel is not None and "0.080 mg/L" in sel["answer_sentence"] and "claim.dbp.mcl.tthm.mcl" in sel["claim_ids"]))
    sel, _ = gen("What is the MRDL for chlorine? For chloramines?")
    results.append(("generate: a two-part question quotes both MRDL claims", sel is not None and {"claim.dbp.mrdl.chlorine-chloramine.mrdl-chlorine", "claim.dbp.mrdl.chlorine-chloramine.mrdl-chloramines"} <= set(sel["claim_ids"])))
    results.append(("generate: disabled returns None", generate("What is the MCLG for chlorite?", retrieve("What is the MCLG for chlorite?", eligible), False) is None))
    # Ari's D4 review (601-604)
    bromate_good = {"claim_ids": ["claim.dbp.mclg.bromate"], "quote_ids": ["quote.dbp.mclg.table"], "answer_sentence": "The MCLG for bromate is zero mg/L.",
                    "conditions_acknowledged": list(next(c for c in pages[0]["claims"] if c["claim_id"] == "claim.dbp.mclg.bromate")["conditions"])}
    expect("the word zero is the number 0 (bromate MCLG)", bromate_good)
    expect("non-zero is not zero: rejected", dict(bromate_good, answer_sentence="The MCLG for bromate is non-zero mg/L."), "numeric-claim-tuple")
    expect("not zero: rejected", dict(bromate_good, answer_sentence="The MCLG for bromate is not zero mg/L."), "numeric-claim-tuple")
    expect("non\u2011zero (non-breaking hyphen) is not zero: rejected", dict(bromate_good, answer_sentence="The MCLG for bromate is non\u2011zero mg/L."), "numeric-claim-tuple")
    expect("nonzero is not zero: rejected", dict(bromate_good, answer_sentence="The MCLG for bromate is nonzero mg/L."), "numeric-claim-tuple")
    expect("zero point eight is not zero: rejected", dict(bromate_good, answer_sentence="The MCLG for bromate is zero point eight mg/L."), "numeric-claim-tuple")
    expect("zero glued to a digit is not zero: rejected", dict(bromate_good, answer_sentence="The MCLG for bromate is zero 8 mg/L."), "numeric-claim-tuple")
    expect("a digit glued to zero is not zero: rejected", dict(bromate_good, answer_sentence="The MCLG for bromate is 1zero mg/L."), "numeric-claim-tuple")
    sel_cor, _ = gen("What corrective action is required after an acute chlorine dioxide MRDL violation?")
    results.append(("generate: a violation question names a metric without being a value question (acute chlorine dioxide violation answered)", sel_cor is not None and "claim.dbp.mrdl.chlorine-dioxide.acute-violation" in sel_cor["claim_ids"]))
    results.append(("asked_metrics: bare 'action' and 'treatment' are not metrics; the phrases are", asked_metrics("What corrective action is required?") == set() and asked_metrics("What is the lead action level?") == {"action-level"} and asked_metrics("Which treatment technique applies?") == {"treatment-technique"}))
    for q in ["What is the maximum residual disinfectant level for bromate?", "What is the maximum contaminant level for chlorine?", "What is the MCL for chlorine?", "What is the MRDL for bromate?"]:
        results.append((f"generate: a value question in a metric no page answers declines: {q}", gen(q)[0] is None))
    results.append(("asked_metrics reads full names and abbreviations", asked_metrics("What is the maximum contaminant level goal for bromate?") == {"mclg"} and asked_metrics("maximum residual disinfectant level for chlorine") == {"mrdl"} and asked_metrics("What is the MCL and MCLG for chlorite?") == {"mcl", "mclg"}))
    draft = json.loads(json.dumps({k: v for k, v in pages[0].items() if k != "_quotes"})); draft["_quotes"] = pages[0]["_quotes"]; draft["status"] = "draft"
    results.append(("generate: never selects from an unsigned page, even when retrieval saw it", generate("What is the MCLG for chlorite?", [(9.0, draft, {})], True) is None and generate("What is the MCLG for chlorite?", [(9.0, pages[0], {})], True) is not None))
    res_decl = answer("What is the MCL for chlorine?", today, True, True)
    results.append(("an enabled generator's decline is INSUFFICIENT_EVIDENCE from quote-or-decline, not the disabled gate", res_decl["selection"] is None and res_decl["disposition"] in ("declined", "retrieval-miss") and not any(r["source_id"] == "generation-disabled" for r in res_decl["envelope"]["outcome_reasons"]) and (res_decl["disposition"] != "declined" or any(r["code"] == "INSUFFICIENT_EVIDENCE" and r["source_id"] == "quote-or-decline" for r in res_decl["envelope"]["outcome_reasons"]))))
    results.append(("generate: nothing retrieved declines", generate("How many days of vacation do operators get?", [], True) is None))
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
