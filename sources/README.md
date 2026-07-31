# Sources

Captured source material and the source registry for the DBP first proof.

- `captures/ecfr-2026-07-01/` holds per-section XML captures of every section
  in the declared rule-family scope (subparts L and V complete, plus 141.2,
  141.53, 141.54, 141.64, 141.65) and subpart Q captured whole, all at eCFR
  point-in-time date 2026-07-01, the same date the page list v0.2 anchors were
  verified against.
- `captures/epa/` holds EPA 816-F-10-080, the comprehensive Stage 1 and
  Stage 2 quick reference guide.
- `capture-manifest-2026-07-31.json` records file, resource URI, capture
  time, sha256, and the verification method for the capture session.
- `source-registry.dbp-first-proof.json` is the source-registry/v0.1
  instance binding authority, authenticity, and maintainer-approved
  reproduction decisions to those digests.

## Interim decision-payload canonicalization

The canonical review-payload serialization algorithm is an open project
decision. Until it is ratified, `decision_payload_sha256` in this registry is
computed as: sha256 of the UTF-8 JSON serialization of the decision object's
`decision_id`, `status`, `classification`, `scope`, and `evidence` fields,
with keys sorted lexicographically and no whitespace (Python
`json.dumps(core, sort_keys=True, separators=(",", ":"))`). This choice is
interim, flagged for review, and every digest will be recomputed under the
ratified canonicalization spec when it lands.
