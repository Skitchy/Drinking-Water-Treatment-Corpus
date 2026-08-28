# Foundry Pass 2: the release gate

Implements Pass 2 brief v0.4 DRAFT
(`proposals/foundry-pass-2-experiment-brief-v0.4-DRAFT.md`, sha256
`31468a1773d8928634e508c5508257c982131e95cbf64553478158a204b5d1c7`, commit
`8a45e78`) with Ari's replacement evaluator packet v0.2 (discussion #8,
comment 18187089): public manifest `3251efde...`; reviewer contract v0.2
`e0909ce4...`; private control bundle `da91e6a8...`, 43,688 bytes; sealed
oracle `58c1b5ec...`, 27,615 bytes, withheld until both reviewer outputs are
fixed. Status: proposed, awaiting a fresh content-bound maintainer
ratification. The v0.3 ratification (18176893, evaluator manifest
`2c6739f3...` at `e7e3945`) was superseded before any reviewer ran; its
control identities were public by design and are treated as burned.

Nothing here is promoted, alters a ratified schema, or claims RFC 005
conformance. Results partition per brief section 9.

## The boundary (brief 7a, built first)

```
adapters/                       engine/
  ecfr_pass1/adapter.py  ---->    contract.py   the interface (the only thing
     (everything eCFR)            |             an adapter and the engine share)
                                  canon.py      declared byte profile + digests
                                  records.py    claim-and-evidence records,
                                                Ari's canonicalization
                                  (next) universe, shards, reviewer harness,
                                         merge, partition, report, manifest
```

An adapter hands the engine three kinds of plain object (`engine/contract.py`):
a **SourceUnit** (source bytes' digest, a canonical representation addressable
by selector, and the anchor rules for that source type including its custody
chain), **Candidates** (a fixed-shape claim payload plus evidence entries,
each an exact quote with a support anchor), and the unit's declared
**ambiguities**. The engine promises the same outputs back for any source.

Rules the tree enforces, not just the prose:

- `engine/` names no source type. `tests/test_boundary.py` greps every engine
  module for eCFR-shaped tokens and fails on a hit; it also fails if an
  engine module imports from `adapters/`.
- The engine's canonicalization is Ari's, proven by round trip: each of the
  21 control records, rebuilt from its payload, evidence, ambiguities, and
  unit through `engine.records.build_record`, reproduces its `record_sha256`,
  `artifact_id`, payload digest, and anchor-set digest exactly.
- The custody chain is data the engine carries and never interprets. eCFR is
  one link (`capture-bytes`). The reserved `ocr-layer` and `page-image` link
  kinds exist so the PDF adapter (a later pass, its own brief) can state its
  extra custody link honestly without an engine change. Pass 2 exercises the
  one-link case only.

Scope guard (Ari, brief 7a): the eCFR adapter consumes the fixed Pass 1
outputs at `4574c8f`. No re-extraction, no PDF or Word adapter, no refactor
of Pass 1.

## Adapter #1: eCFR from Pass 1

Pass 1 emitted eight claim fields. The contract payload carries nine, the
three Pass 1 never emitted (`applicability`, `effective_time`,
`dependencies`) filled empty by the adapter, exactly as Ari's control records
fill them. So natural and control records share one shape and one digest
rule, and a shard cannot tell them apart by field.

Natural release universe: 387 verified claims across 37 of 38 sections
(141.210 has none). All 387 build and verify against their units.

## Tests

```
cd experiments/foundry-pass-2 && python3 -m unittest tests.test_boundary -v
```

## Pipeline (built 2026-08-27, in this order)

| Step | Where | State |
| --- | --- | --- |
| Boundary | `engine/contract.py`, `adapters/ecfr_pass1/` | committed `c711f06`, 8 tests |
| Review-input bundle | `engine/universe.py`, `tools/emit_bundle.py` | emitted: 408 records (387 natural + 21 controls), 37 shards, class-1 replay identical |
| Reviewer A harness | `engine/reviewer.py`, `tools/run_reviewer_a.py` | built; identity + 5 leak probes bind before any review; offline-tested against Ari's validator |
| Release gate | `engine/gate.py`, `tools/run_gate.py` | built; merge, partition, report, candidate, manifest; 5 tests incl. class-1 replay |
| Control grading | Ari's `grade-mixed-controls-v0.1.py` after oracle reveal | not run |

**Pre-run privacy (Ari review 2026-08-27, brief v0.4 draft):** `out/shards/`,
`out/review-universe.json`, `out/shard-manifest.json`, and `out/sealed/` are
git-ignored until both reviewer outputs are fixed; the natural Pass 1
outputs are public, so a public mixed universe would reveal the controls by
subtraction. Only `out/review-input-bundle.json` (digests and commitments)
is committed pre-run. Replacement controls come from Ari outside git:
`python3 tools/emit_bundle.py --controls <private path>`.

**Gate hardening after the review:** typed PASS/FAIL/PENDING/MISSING gates,
issuance only on all-PASS including control grading and class-1 replay;
reviewer outputs validated in-gate; identity records checked mechanically
against the bound artifacts they name (a well-formed but wrong digest fails);
each reviewer's run-record manifest (probe transcript, identity, shard run
records, outputs) verified member by member and bound into the release
manifest. 28 tests.

Reviewer B (Ari's lineage) consumes the same `out/shards/` bytes and returns
schema-valid outputs to `out/reviewer-b/outputs/` plus an identity record.

Coverage per planned concept (brief 4a) is not computed by the engine: the
Pass 1 concept reference is the evaluator-held 40-question bank, not a list
in the canonical index. Reported as such in the release report; the
evaluator grades it after reveal.
