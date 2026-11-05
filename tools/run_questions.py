#!/usr/bin/env python3
"""Run the DBP question bank through the answer path and report raw counts
per Charter v1.1, Done item 5.

Usage: run_questions.py --run-kind first-run|rerun [--today YYYY-MM-DD]
         [--allow-stale-dev] [--generate] [--questions PATH] [--out DIR]

Exit codes: 0 bar met; 2 bar not met (or run not scorable); 1 crash or
envelope schema failure. --selftest runs the grading and bar checks offline. A run under --allow-stale-dev is never scorable and
is labeled NOT A SCORED RUN in every output.
"""
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import answer_path  # noqa: E402

DEFAULT_QUESTIONS = ROOT / "evaluation" / "questions.dbp-v0.1.json"
DEFAULT_OUT = ROOT / "out" / "answer-path"
BAR = {"accuracy_min": 0.98, "coverage_min": 0.90}


def arg(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


ANSWERED = ("correct", "wrong", "needs-review", "rejected", "fabricated", "failed_quote")


def grade(q, res):
    """One of: correct, needs-review, wrong, rejected, fabricated, failed_quote, declined.
    Anything with a selection is ANSWERED (Charter v1.1 item 5: a wrong answer is
    never reclassified as a decline). 'declined' means no selection was made."""
    if res.get("selection") is None:
        return "declined"
    kinds = {f[0] for f in res.get("validation_failures", [])}
    if kinds & {"claim-resolution", "quote-resolution"}:
        return "fabricated"
    if "span-fidelity" in kinds:
        return "failed_quote"
    if kinds:
        return "rejected"
    env = res["envelope"]
    if env["outcome"] not in ("evidence-backed", "evidence-only"):   # evidence-only: a dev-waived gate on a cited page; never in a scored run
        return "rejected"
    cited = {r["claim_id"] for r in env["claim_refs"]}
    sentence = (res["selection"] or {}).get("answer_sentence", "") or ""
    want_claims = set(q.get("expected_claim_ids") or [])
    values = q.get("expected_values") or []
    values_ok = bool(values) and all(v.lower() in sentence.lower() for v in values)
    claims_ok = want_claims <= cited
    if not values_ok or not claims_ok:
        return "wrong"
    if q.get("flag"):
        return "needs-review"  # automation cannot establish correctness; a human must
    return "correct"


def tally(rows, dev, gen):
    def n(pred):
        return sum(1 for r in rows if pred(r))
    supported = [r for r in rows if r["label"] == "supported"]
    oos = [r for r in rows if r["label"] == "out-of-scope"]
    pending = [r for r in rows if r["label"] not in ("supported", "out-of-scope")]
    answered = [r for r in supported if r["grade"] in ANSWERED]
    counts = {
        "questions_total": len(rows), "supported": len(supported), "out_of_scope": len(oos), "pending_label": len(pending),
        "answered_supported": len(answered),
        "correct": n(lambda r: r["label"] == "supported" and r["grade"] == "correct"),
        "needs_review": n(lambda r: r["grade"] == "needs-review"),
        "wrong": n(lambda r: r["label"] == "supported" and r["grade"] == "wrong"),
        "rejected_by_validation": n(lambda r: r["grade"] == "rejected"),
        "failed_quote": n(lambda r: r["grade"] == "failed_quote"),
        "fabricated_citations": n(lambda r: r["grade"] == "fabricated"),
        "declined_supported": n(lambda r: r["label"] == "supported" and r["grade"] == "declined"),
        "out_of_scope_correct_declines": n(lambda r: r["label"] == "out-of-scope" and r["grade"] == "declined"),
        "out_of_scope_answered": n(lambda r: r["label"] == "out-of-scope" and r["grade"] != "declined"),
        "pending_label_answered": n(lambda r: r["label"] not in ("supported", "out-of-scope") and r["grade"] != "declined"),
        "retrieval_hit_expected_page": n(lambda r: r["retrieved"] and any(p["page_id"] in r["expected_page_ids"] for p in r["retrieved"])),
        "retrieval_any": n(lambda r: bool(r["retrieved"])),
    }
    accuracy = counts["correct"] / len(answered) if answered else None
    coverage = len(answered) / len(supported) if supported else None
    unassigned = [r for r in rows if r["safety"] is None]
    tagged = [r for r in rows if r["safety"] is True]
    unsafe = [r for r in tagged if r["grade"] in ("wrong", "rejected", "fabricated", "failed_quote")]
    safety = {"unassigned": len(unassigned), "tagged": len(tagged),
              "tagged_correct": sum(1 for r in tagged if r["grade"] == "correct"),
              "tagged_declined": sum(1 for r in tagged if r["grade"] == "declined"),
              "tagged_needs_review": sum(1 for r in tagged if r["grade"] == "needs-review"),
              "unsafe_answers": len(unsafe), "unsafe_ids": [r["id"] for r in unsafe]}
    bar = {
        "zero_fabricated": counts["fabricated_citations"] == 0,
        "zero_failed_quotes": counts["failed_quote"] == 0,
        "accuracy_ge_98": accuracy is not None and accuracy >= BAR["accuracy_min"],
        "coverage_ge_90": coverage is not None and coverage >= BAR["coverage_min"],
        "all_out_of_scope_declined": counts["out_of_scope_answered"] == 0,
        "no_unsafe_answer": len(unsafe) == 0,
        "scorable": (not dev) and gen and not pending and bool(oos) and not unassigned and counts["needs_review"] == 0,
    }
    not_scorable_because = []
    if dev: not_scorable_because.append("dev override")
    if not gen: not_scorable_because.append("generation off")
    if pending: not_scorable_because.append(f"{len(pending)} question(s) with a pending label")
    if not oos: not_scorable_because.append("no out-of-scope questions in the bank")
    if unassigned: not_scorable_because.append(f"{len(unassigned)} safety judgment(s) unassigned")
    if counts["needs_review"]: not_scorable_because.append(f"{counts['needs_review']} answer(s) need human review")
    return counts, accuracy, coverage, safety, bar, all(bar.values()), not_scorable_because


def selftest():
    """Grading and bar logic against synthetic results; each case failed on the session-1 code."""
    def res(selection, failures=(), outcome="abstention", cited=()):
        return {"selection": selection, "validation_failures": list(failures),
                "envelope": {"outcome": outcome, "claim_refs": [{"claim_id": c} for c in cited], "outcome_reasons": []}, "retrieved": []}
    q = {"id": "T", "label": "supported", "safety": None, "flag": None, "expected_claim_ids": ["claim.x"], "expected_values": ["0.8"], "expected_page_ids": []}
    sel = {"claim_ids": ["claim.x"], "quote_ids": ["quote.x"], "answer_sentence": "It is 0.8 mg/L."}
    out = []
    out.append(("numeric rejection is answered-and-wrong, not declined", grade(q, res(sel, [("numeric-claim-tuple", "claim.x", "")])) == "rejected"))
    out.append(("coverage rejection is answered-and-wrong, not declined", grade(q, res(sel, [("coverage", "envelope", "")])) == "rejected"))
    out.append(("no selection is declined", grade(q, res(None)) == "declined"))
    out.append(("expected claim ids alone are not correct", grade(q, res(dict(sel, answer_sentence="It is 1.0 mg/L."), outcome="evidence-backed", cited=["claim.x"])) == "wrong"))
    out.append(("values plus claims, unflagged -> correct", grade(q, res(sel, outcome="evidence-backed", cited=["claim.x"])) == "correct"))
    out.append(("values plus claims, flagged -> needs-review", grade(dict(q, flag="confirm wording"), res(sel, outcome="evidence-backed", cited=["claim.x"])) == "needs-review"))
    def row(label, grade_, safety):
        return {"id": label, "label": label, "grade": grade_, "safety": safety, "retrieved": [], "expected_page_ids": []}
    base = [row("supported", "correct", False)] * 50 + [row("out-of-scope", "declined", False)]
    _, _, _, _, bar, met, why = tally(base, dev=False, gen=True)
    out.append(("clean synthetic run meets the bar", met and not why))
    out.append(("pending label blocks scorable", not tally(base + [row("pending-D1", "declined", False)], False, True)[4]["scorable"]))
    out.append(("zero out-of-scope blocks scorable", not tally([row("supported", "correct", False)] * 50, False, True)[4]["scorable"]))
    out.append(("unassigned safety blocks scorable", not tally(base + [row("supported", "correct", None)], False, True)[4]["scorable"]))
    out.append(("needs-review blocks scorable", not tally(base + [row("supported", "needs-review", False)], False, True)[4]["scorable"]))
    out.append(("generation off blocks scorable", not tally(base, False, False)[4]["scorable"]))
    out.append(("tagged-but-safe correct answer does not block", tally(base + [row("supported", "correct", True)], False, True)[5]))
    out.append(("tagged unsafe (wrong) answer blocks", not tally(base + [row("supported", "wrong", True)], False, True)[4]["no_unsafe_answer"]))
    out.append(("tagged unsafe (validation-rejected) answer blocks", not tally(base + [row("supported", "rejected", True)], False, True)[4]["no_unsafe_answer"]))
    out.append(("rejected answers count in the accuracy denominator", tally(base + [row("supported", "rejected", False)] * 2, False, True)[1] == 50 / 52))
    for name, ok in out:
        print(("PASS " if ok else "FAIL ") + name)
    print(f"{sum(1 for _, o in out if o)}/{len(out)} passed")
    return all(o for _, o in out)


def main(argv):
    if argv[:1] == ["--selftest"]:
        sys.exit(0 if selftest() else 1)
    run_kind = arg(argv, "--run-kind")
    if run_kind not in ("first-run", "rerun"):
        print(__doc__, file=sys.stderr); sys.exit(2)
    today = dt.date.fromisoformat(arg(argv, "--today", dt.date.today().isoformat()))
    dev = "--allow-stale-dev" in argv
    gen = "--generate" in argv
    bank = json.load(open(arg(argv, "--questions", DEFAULT_QUESTIONS), encoding="utf-8"))
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(arg(argv, "--out", DEFAULT_OUT)) / f"{run_kind}-{stamp}{'-DEV-NOT-SCORED' if dev else ''}"
    (out / "envelopes").mkdir(parents=True)

    rows = []
    for q in bank["questions"]:
        res = answer_path.answer(q["question"], today, dev, gen, answer_id=f"answer.{q['id']}-{stamp}")
        g = grade(q, res)
        (out / "envelopes" / f"{q['id']}.json").write_text(json.dumps(res["envelope"], indent=2) + "\n", encoding="utf-8")
        rows.append({"id": q["id"], "label": q["label"], "safety": q["safety"], "grade": g,
                     "disposition": res["disposition"], "outcome": res["envelope"]["outcome"],
                     "reasons": sorted({r["code"] for r in res["envelope"]["outcome_reasons"]}),
                     "retrieved": res["retrieved"],
                     "expected_page_ids": q["expected_page_ids"]})

    counts, accuracy, coverage, safety, bar, met, why = tally(rows, dev, gen)
    report = {
        "run_kind": run_kind, "scored_run": bar["scorable"],
        "label": "NOT A SCORED RUN (dev override --allow-stale-dev)" if dev else ("scored run" if bar["scorable"] else "NOT SCORABLE: " + "; ".join(why)),
        "today": today.isoformat(), "generation_enabled": gen, "generated_at": stamp,
        "questions_file": str(arg(argv, "--questions", DEFAULT_QUESTIONS)),
        "drift_report": answer_path.latest_drift_report() and answer_path.latest_drift_report()["_path"],
        "counts": counts, "accuracy": accuracy, "coverage": coverage, "safety": safety,
        "bar": bar, "bar_met": met, "not_scorable_because": why, "rows": rows,
    }
    (out / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    node = subprocess.run(["node", str(ROOT / "tools" / "check_envelopes.mjs"), str(out / "envelopes")], capture_output=True, text=True)
    print(report["label"].upper())
    print(f"run_kind={run_kind} today={today} generation={'on' if gen else 'off'} out={out.relative_to(ROOT)}")
    for k, v in counts.items():
        print(f"  {k:32s} {v}")
    print(f"  accuracy (correct/answered)      {accuracy if accuracy is not None else 'undefined (0 answered)'}")
    print(f"  coverage (answered/supported)    {coverage if coverage is not None else 'undefined'}")
    print("  safety: " + ", ".join(f"{k}={v}" for k, v in safety.items() if k != "unsafe_ids") + (f" ids={safety['unsafe_ids']}" if safety["unsafe_ids"] else ""))
    print("  bar: " + ", ".join(f"{k}={'ok' if v else 'NO'}" for k, v in bar.items()) + f" -> {'MET' if met else 'NOT MET'}")
    print("  envelope schema check: " + node.stdout.strip().replace("\n", " | "))
    if node.returncode != 0:
        print(node.stderr, file=sys.stderr); sys.exit(1)
    sys.exit(0 if met else 2)


if __name__ == "__main__":
    main(sys.argv[1:])
