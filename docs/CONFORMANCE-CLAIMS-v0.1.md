# Renderer conformance claims v0.1

This policy is the enforcement instrument for acceptance case AT-014. It does
not claim technical control over arbitrary third-party code.

An implementation may describe itself as a **conforming renderer** only when
the published renderer-conformance suite demonstrates that it:

1. accepts only schema-valid, semantically validated, integrity-bound answer
   envelopes from a compatible runtime assurance manifest;
2. resolves claim, selected table-cell, and quote IDs only from the named
   immutable corpus release;
3. renders human-readable answer content only through the template set pinned
   by the runtime assurance manifest;
4. does not display arbitrary narrative fields or unchecked model output as
   part of the validated answer;
5. displays the outcome class, evidence references, applicable narrow check
   labels, and limitations required by the assurance contract;
6. keeps auxiliary host content visually and structurally separate; and
7. leaves auxiliary content disabled by default in the reference
   verified-evidence mode.

A nonconforming client may consume the gateway protocol, but it may not claim
the project's display assurance or use project conformance marks. The gateway
guarantees its own output boundary; this policy governs what a client may
claim about its display behavior.

Conformance is version-specific. A renderer must name the runtime assurance
manifest and conformance-suite version it passed.
