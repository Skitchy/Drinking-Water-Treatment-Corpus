# Foundry Pass 2: the release gate

Implements the ratified Pass 2 brief v0.3
(`proposals/foundry-pass-2-experiment-brief-v0.3.md`, sha256
`6e83818e106f494bb2101472ef7fa1e65c249a3ad78b35cb02075205bfb0132b`, commit
`809c663`) under the maintainer's content-bound ratification (discussion #8,
comment 18176893): one quarantined, non-production experiment; evaluator
manifest `2c6739f3...` at `e7e3945`; sealed oracle `f3364e08...`, 16,548
bytes, withheld until both reviewer outputs are fixed.

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
