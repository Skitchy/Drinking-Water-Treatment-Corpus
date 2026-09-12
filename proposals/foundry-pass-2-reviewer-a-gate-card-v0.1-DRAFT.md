# Foundry Pass 2 — Reviewer A Clearance Gate Card v0.1 (DRAFT)

**Purpose.** Decide whether one exact Reviewer A harness head is technically ready for a
separately authorized identity-binding decision. This card grants no execution authority.

## Current gate

| Field | Value |
| --- | --- |
| Phase | Reviewer A harness integrity, before identity binding |
| Candidate | `3c843636dcd37c0f6d87b4c07256c2c587e44926` |
| Parent | `7caff55e6bd50bc5d48f47c6d53c2f4e2828c6c8` |
| Current disposition | **NOT CLEAR** |
| Sole current blocker | Command-level `model_calls`, `cli_invocations`, `call_ceiling`, and `attempts_allowed` accept JSON lookalikes (`true`, `1.0`) as exact integers; altered PASS evidence can host a later command. |
| Backlog, not blocking this gate | A forged replacement for the identity's own binding record can silence a standalone store/status warning, but the governed review path still refuses before a session. |
| Prior authority | Discussion #8 comment `18391672`; consumed by `3c84363` |
| Decision owner | Skitch, as maintainer |
| Implementer / independent reviewer | CC / Ari |

## Definition of Clear

### 1. Boundary and threat model

Assume a crash, partial write, or local mutation can add, remove, replace, re-address,
link, or corrupt anything in the mutable evidence root. Tracked code and bound inputs can
drift and must match the exact Git head and installed identity. Trust collision-resistant
hashes, the maintainer's external ruling, and successful operating-system regular-file,
no-follow, atomic-link/replace, and fsync guarantees.

This gate does **not** claim to detect a wholesale self-consistent forgery when every
referrer and artifact lives in the same mutable root with no external anchor. State such
limits; do not silently treat them as proved away.

### 2. A finding blocks CLEAR only when execution or direct code proof shows that it can

- start an unauthorized, duplicate, wrong-model, wrong-head, or over-budget invocation;
- produce or preserve a false `PASS`, `DONE`, or clean prior-command state;
- misbind the ruling, identity, configuration, input, output, reservation, claim, record,
  or required digest;
- silently lose, truncate, overwrite, follow, or misreport durable evidence; or
- let an unsafe prior state host another governed command instead of refusing or
  quarantining it.

Wording, redundant defense, diagnostics that cannot cross the pre-session boundary,
speculative hardening, and documented out-of-model behavior go to a backlog. Promotion to
blocker requires a minimal reproduction or direct proof tied to a rule above.

### 3. Required evidence on the final candidate bytes

1. **Identity and scope:** candidate, sole parent, live branch, changed-file list, clean
   tracked tree, authorization, and Discussion report agree. Only authorized behavior
   changed; governed evidence and bound packet bytes did not.
2. **Focused closure:** every previously blocking reproduction in the authorized scope now
   refuses before a session, with a legitimate control still accepted. For the present
   blocker, strict integer checks must explicitly reject booleans and non-integer JSON
   numbers for all four command-level fields, report the prior command inconsistent, and
   prevent the next command.
3. **Suites:** the implementer records one passing public and private offline suite on the
   final tree with `ResourceWarning` fatal, bytecode disabled, and the governed model
   unavailable. The independent reviewer reruns the public suite and focused probes and
   verifies the private receipt without exposing sealed material.
4. **Mutation checks:** an unmutated control passes and every non-equivalent targeted mutant
   is killed. An allowed survivor needs a mechanistic equivalence explanation and reviewer
   agreement. Production-code changes restart the targeted matrix. A test-only pin reruns
   the survivor, control, and both suites—not already-killed mutants unless shared fixtures
   or matrix generation changed.
5. **Independent review:** one exact-diff review checks changed logic, reproductions,
   receipts, stated limits, and the blocker rules. Peer agreement is evidence, not authority.

### 4. Stopping and change-freeze rule

When all evidence passes and no qualifying blocker remains, the reviewer issues **CLEAR at
`<exact SHA>`** and stops exploratory widening. New non-blockers enter the backlog. Any
tracked-byte change invalidates CLEAR and needs proportionate review under fresh authority.

A NOT CLEAR disposition gives one minimal reproduction per blocker and returns the decision
to Skitch; it authorizes no fix. CLEAR is exact-head technical evidence only. Identity
binding and any real shard remain separate maintainer decisions. CLEAR never authorizes a
model/reviewer run, commit, push, merge, publication, release, installation, migration, or
deployment.

## Approval

- CC technical/operational review: **pending**
- Ari independent-review criteria: **drafted; pending maintainer approval**
- Skitch threat-model, severity, and stopping-rule approval: **pending**
