# Versioned assurance schemas

These JSON Schema 2020-12 documents turn the accepted RFC vocabulary into
machine-checkable shapes:

- `drinking-water-profile-v0.1.schema.json` validates a normalized JSON
  representation of an OKF concept page and its Drinking Water Assurance
  Profile extension fields.
- `reviewer-registry-v0.1.schema.json` defines the minimum credible registry,
  even while the project has only one reviewer.
- `verified-answer-v0.1.schema.json` defines the gateway's native answer
  envelope. It deliberately has no arbitrary narrative field.
- `audit-envelope-v0.1.schema.json` records enough retrieval and validation
  state to investigate a decision without asserting that a full audit system
  already exists.

## Three validation layers

1. **Schema-valid:** required fields, types, enums, and closed envelope
   surfaces match the versioned schema.
2. **Semantically validated:** referenced claim, quote, page, reviewer, and
   release IDs exist; duplicated digests and canonical values match; policy
   gates and declared checks pass.
3. **Integrity-bound:** the canonical envelope bytes match the recorded
   digest. `Sealed` additionally requires a verifiable signature.

JSON Schema alone cannot establish semantic truth or compare a review event's
digest with canonical page bytes. Those requirements are named in `$comment`
annotations and exercised by the acceptance-test contract.

## Compatibility policy

The profile permits unknown extension fields so that the normalized record
can remain OKF-compatible. The answer and audit envelopes are closed:
unrecognized fields fail validation, which prevents a client from smuggling
unchecked narrative into a verified-answer object.

Every incompatible change requires a new schema version. Published corpus
releases and answer envelopes name the exact version they use.
