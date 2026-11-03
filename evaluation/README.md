# Evaluation

`questions.dbp-v0.1.json` is the DBP question bank as structured data, built
by `tools/build_questions.py` from `docs/EPA_DBP_Challenge_Questions.md`
(question and answer-key text verbatim). Labels, expected page and claim IDs,
expected values and flags are CC's draft (2026-11-01) for Skitch's
confirmation; `confirmed_by_skitch` is false on every item until he signs.
Labels and rulings live in the ANNOTATIONS table inside `build_questions.py`,
so they survive a rebuild; run `build_questions.py --check` to confirm the
JSON matches a fresh build. Decision D1 (Skitch, 2026-11-01) labels Q1, Q2,
Q6, Q16 and Q24 `out-of-scope` with `label_reason` "EPA guide only". `safety`
is null (unassigned) until Skitch assigns true or false per question.

`dbp-page-list-v1.0.json` is the frozen 17-page list (Charter v1.1 Done item
1, decision D2) with the fold-in claim mapping and the excluded sections.

Run the bank: `python3 tools/run_questions.py --run-kind first-run` or
`--run-kind rerun`; add `--allow-stale-dev` to exercise retrieval on stale
pages (never a scored run). A run is scorable only when generation is on, no
label is pending, the bank has out-of-scope questions, every safety judgment
is assigned, and no answer needs human review; otherwise the header says why.
Results and one verified-answer/v0.1 envelope per question land under
`out/answer-path/` (gitignored); envelopes are schema-checked by
`tools/check_envelopes.mjs`. `run_questions.py --selftest` checks the grading
and bar logic offline.

Freshness: `tools/source_watch.py drift` writes `sources/watch/drift-<date>.json`
(the live watch result the answer path reads); `tools/renew_page.py <page_id>`
writes `pages/renewals/<page_id>.renewal-<date>.json` (decision D3), which
extends a page's expiry without touching its signed payload when every source
is unchanged.
