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

## Foundation fixtures

The fixtures are synthetic and are not regulatory evidence:

- one valid reviewer registry and stable profile;
- one invalid profile with a stale human-review digest;
- a synthetic release index for ID and digest resolution;
- valid examples for all three answer outcomes;
- mutations that test free-text injection, unknown claims, and release-digest
  mismatch.

Run the dependency-free foundation checks from the repository root:

```sh
node tests/acceptance/check-artifacts.mjs
```

The script checks JSON parseability, expected schema versions, review-payload
binding, the closed answer surface, outcome invariants, and claim/quote/release
resolution. A standards-complete JSON Schema validator and canonicalization
test vectors remain explicit next actions in `PROJECT-STATE.md`.
