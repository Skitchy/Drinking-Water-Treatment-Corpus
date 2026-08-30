# Foundry Pass 2 isolated review task

Contract SHA-256: `{{CONTRACT_SHA256}}`

Review-input bundle SHA-256: `{{REVIEW_INPUT_BUNDLE_SHA256}}`

Shard manifest SHA-256: `{{SHARD_MANIFEST_SHA256}}`

Reviewer identity SHA-256: `{{REVIEWER_IDENTITY_SHA256}}`

Review shard ID: `{{SHARD_ID}}`

Output schema SHA-256: `{{OUTPUT_SCHEMA_SHA256}}`

Apply the system prompt and reviewer contract to the supplied shard. The deterministic harness has already recomputed and verified every record's artifact-ID derivation, claim-payload digest, normalized-support-anchor-set digest, and record digest; no tools are available, so do not emit tool calls, shell commands, or prose, and preserve those supplied identities exactly in your JSON disposition while assessing semantic support from the supplied shard content. Inspect the complete supplied source context, not only the selected quotation.

Return one schema-valid JSON object. Its `dispositions` array must contain every artifact ID in the shard exactly once. Preserve the submitted digests in each disposition. Use only the controlled reason codes declared by the contract. An `accept` disposition has no reasons and no proposed correction. A `correct` disposition includes a complete replacement claim payload and/or support-anchor set. `reject` and `abstain` do not include a correction.

Your entire response must be one JSON object that validates against the following JSON Schema. These are the exact bytes of the bound output schema; the field names and enumerations it declares are the only ones accepted.

--- BEGIN OUTPUT SCHEMA ---

{{OUTPUT_SCHEMA_JSON}}

--- END OUTPUT SCHEMA ---

The content-bound shard follows this separator:

--- BEGIN REVIEW SHARD ---

{{REVIEW_SHARD_JSON}}

--- END REVIEW SHARD ---
