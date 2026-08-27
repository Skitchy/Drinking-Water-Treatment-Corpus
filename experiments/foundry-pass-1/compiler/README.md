# Foundry Pass 1 Compiler

Implementation of the measured, non-production eCFR compiler pass under the
converged experiment brief (`proposals/foundry-pass-1-experiment-brief-v0.1.md`,
v0.1.2) and the maintainer's execution authorization
(discussions/8 comment 17868369, citing evaluator manifest
`dcd448e615bf197c463c8bed7fbb7e18a9c0dbf3b61bf9560b99eaafa04f8ea3` and sealed
oracle `285d5e5a7abfc3c757edb8aaeae35d6941c41cc1312b0bca2078c49d27254ae6`).

Everything this compiler writes lives under `experiments/foundry-pass-1/`.
It reads, and never writes, `sources/` and `schemas/`. Nothing here is
promoted, nothing alters ratified schemas, and nothing claims RFC 005
conformance. All results are partitioned per brief section 9.

## Stages

| Stage | Module | Function |
| --- | --- | --- |
| 0 | `foundry_lib.py` | Closed-input verification: every member of the evaluator-prepared input manifest checked by path, byte length, and sha256. Fail closed per capture; a failed capture emits nothing downstream. |
| 1 | `canonicalize.py` | Captured XML to canonical normalized representation (declared byte profile below), content-digested. |
| 2 | `canonicalize.py` | Dual anchors: representation-bound selectors (authoritative) plus derived logical citation anchors (metadata; ambiguity becomes a review item, never a guess). |
| 3 | `extraction/` | Isolated extraction role: fresh session, bundle-only inputs, recorded prompt/allowlist digests, executable isolation probes. |
| 4 | `verify_candidates.py` | Machine verification of candidate material: span digests recomputed from canonical bytes, every referenced ID resolved (selection, not authorship). |
| 5 | `project_reviewer.py` | Class-1 deterministic reviewer projection per candidate page; WIP cap of 5 enforced at emission. |

## Declared canonical byte profile (brief section 7)

Canonical payloads are JSON serialized exactly as: UTF-8, LF newlines, keys
sorted lexicographically, separators `,` and `:` with no insignificant
whitespace, one trailing LF. Content digests are sha256 over exactly those
bytes. Run/event envelopes (time, actor, environment, execution ID) live in
separate class-2 files and are excluded from replay comparison.

## Declared XML normalization

- Parsing: Python stdlib `xml.etree.ElementTree` (entities resolved by the
  parser; no external DTD fetching).
- Text: Unicode NFC; internal whitespace runs collapsed to a single space;
  leading and trailing whitespace stripped per text block.
- Structure: element order preserved; tables kept structural (rows and cells
  with 1-based coordinates), never flattened to prose.
- Node selectors: deterministic path of `TAG[i]` segments, `i` the 1-based
  index among same-tag siblings; `DIV8` segments keyed by their `N`
  attribute as `DIV8[N=<value>]`.
- Raw byte ranges recorded only when the represented text is contiguous in
  the captured bytes; their absence is not a defect.

## Anchors

The representation-bound selector (capture digest, node selector, character
offsets in normalized node text, span digest) is the sole authoritative
binding. The logical citation anchor (for example `141.53(a)(1)`) is derived
metadata; Ari operates an independent derivation sharing no code with this
one, and divergence is a review item neither side resolves alone.

## Determinism rules for this codebase

Stdlib only. No wall-clock, randomness, locale, or dict-order dependence in
any canonical payload. Envelope data is written by the orchestrator into
`run-record` class-2 files only. Failure logs are append-only JSON lines with
chained content-addressed heads.
