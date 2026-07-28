# v0.1 adversarial acceptance contract

This directory translates RFC 003 section 11 and the accepted renderer
boundary into named acceptance cases. The manifest is machine-readable; the
fixtures establish the initial schema and semantic-resolution foundation.

This is not a claim that a gateway, renderer, source watcher, or production
corpus already passes the suite. Cases marked `specified` remain release
requirements to automate when their component exists.

## Validation layers

- **Schema:** JSON shape, required fields, enums, closed answer surface.
- **Semantic:** identifiers resolve against the named immutable release,
  digests agree, review events bind to the current payload, and policy
  invariants hold.
- **Integration:** retrieval, watch, gateway, transport, and renderer behavior
  is observed end to end.

Passing a schema test does not imply passing a semantic or integration test.

## Minimum cases

| ID | Required behavior | Layer |
| --- | --- | --- |
| AT-001 | A post-review payload change invalidates human-reviewed eligibility. | Semantic |
| AT-002 | A correct number attached to the wrong unit, parameter, jurisdiction, or system type fails. | Semantic |
| AT-003 | A quote omitting a material exception cannot become stable without context-completeness review. | Semantic |
| AT-004 | A stale page cannot produce an evidence-backed answer under strict policy. | Integration |
| AT-005 | An out-of-coverage question produces explicit abstention. | Integration |
| AT-006 | Failed or overdue source watches fail closed. | Integration |
| AT-007 | A source correction identifies and gates every dependent page. | Integration |
| AT-008 | A retrieval miss is not rendered as proof that no requirement exists. | Integration |
| AT-009 | An MCP-only integration does not advertise enforced answer checking. | Integration |
| AT-010 | Verified-evidence mode exposes no unchecked streamed text. | Integration |
| AT-011 | An arbitrary narrative field is rejected by the answer schema. | Schema |
| AT-012 | An unknown or mismatched claim ID is rejected semantically. | Semantic |
| AT-013 | A mismatched corpus manifest digest is rejected semantically. | Semantic |
| AT-014 | Display-assurance language is available only to a conforming renderer. | Integration |
| AT-015 | Auxiliary host content is separate, disclosed, and disabled by default in the reference verified-evidence mode. | Integration |
| AT-016 | A missing policy-mandatory check rejects an evidence-backed envelope. | Semantic |
| AT-017 | Mandatory checks cover every applicable claim, quote, page, and envelope subject. | Semantic |
| AT-018 | Every outcome reason traces to a permitted failed check or policy gate. | Semantic |
| AT-019 | Invalid dates and timestamps fail format assertion. | Schema |
| AT-020 | Every ineligible retrieval candidate records an explanation. | Schema |
| AT-021 | Watch status becomes overdue from time even when the stored result says unchanged. | Semantic |
| AT-022 | Stable evidence resolves to an approved content-bound reproduction decision. | Semantic |
| AT-023 | Human and process verification scopes cannot be interchanged. | Schema |
| AT-024 | A quote's captured-source digest matches its resolved source snapshot. | Semantic |
| AT-025 | Applicability population bounds are ordered. | Semantic |
| AT-026 | Reviewer qualifications cover the review-event timestamp. | Semantic |
| AT-027 | Page-local source, quote, and claim IDs are unique. | Semantic |
| AT-028 | Derived-claim dependency graphs are acyclic. | Semantic |
| AT-029 | Schema identifiers are immutable logical URIs. | Schema |
| AT-030 | Answer and runtime assurance manifest digests agree. | Semantic |
| AT-031 | A runtime manifest cannot weaken the assurance-contract mandatory-check baseline. | Semantic |
| AT-032 | A table claim missing a row-band and column-band cell is rejected. | Semantic |

## Foundation fixtures

The fixtures are synthetic and are not regulatory evidence:

- valid reviewer and source registries plus a stable profile;
- one invalid profile with a stale human-review digest;
- separate synthetic corpus-release and runtime-assurance manifests;
- an audit record with one rejected and one accepted generation attempt;
- valid examples for all three answer outcomes;
- mutations covering the schema-ratification findings.

Install the locked test dependencies and run the foundation checks:

```sh
npm ci
npm test
```

The script runs AJV 2020-12 with format assertion, then checks review-payload
binding, licensing resolution, actor scopes, effective watch state, the closed
answer surface, policy-mandatory check coverage, structured outcome causes,
manifest compatibility, claim/quote/source resolution, reviewer qualification
timing, bounds, uniqueness, derivation cycles, and table-claim band and cell coverage. Canonicalization
conformance vectors remain an explicit next action in `PROJECT-STATE.md`.
