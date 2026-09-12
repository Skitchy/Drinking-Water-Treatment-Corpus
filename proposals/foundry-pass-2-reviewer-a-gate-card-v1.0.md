# Foundry Pass 2 — Reviewer A Clearance Gate Card v1.0

**Purpose.** Decide whether one exact Reviewer A harness head is technically ready for a
separately authorized identity-binding decision. This card grants no execution authority.

## Current gate

| Field | Value |
| --- | --- |
| Phase | Reviewer A harness integrity, before identity binding |
| Candidate | `3c843636dcd37c0f6d87b4c07256c2c587e44926` |
| Parent | `7caff55e6bd50bc5d48f47c6d53c2f4e2828c6c8` |
| Current disposition | **NOT CLEAR** |
| Sole current blocker | Python value/type checks admit JSON booleans or non-integer numbers at count, ceiling, and attempt-limit sites; altered evidence can remain clean and host a later command. |
| Backlog, not blocking this gate | Ari reproduced: replacing the identity's own binding record can silence a standalone store/status warning for added artifacts, but the governed review path still refuses before a session. CC had not reproduced this item when reviewing v0.1. |
| Prior authority | Discussion #8 comment `18391672`; consumed by `3c84363` |
| Card decision | Discussion #8 comment `18404556` approves the v0.1 review changes and authorizes this v0.2 draft only |
| Decision owner | Skitch, as maintainer |
| Implementer / independent reviewer | CC / Ari |
| Isolated adversary pass on closes | Required before push; repeat after a blocking close until one pass reports zero blockers; report total pass count and final result |

## Definition of Clear

### 1. Boundary and threat model

Assume a crash, partial write, or local mutation can add, remove, link, rename, re-address,
or corrupt anything in the mutable evidence root. Tracked code and bound inputs can drift
and must match the exact Git head and installed identity. Trust collision-resistant hashes,
the maintainer's external ruling, and successful operating-system regular-file, no-follow,
atomic-link, rename, and fsync guarantees.

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
speculative hardening, and documented out-of-model behavior go to a backlog. Every backlog
entry names who reproduced it. Promotion to blocker requires a minimal reproduction or
direct proof tied to a rule above.

### 3. Required evidence on the final candidate bytes

1. **Identity and scope:** candidate, sole parent, live branch, clean tracked tree,
   authorization, and Discussion report agree. The changed-file list is a subset of the
   files named by the authorization. `engine/reviewer.py`, the packet, prompts, schema,
   evaluator, adapter, configuration, and governed evidence hash unchanged.
2. **Focused closure:** every authorized blocker refuses before a session, with a legitimate
   control accepted. For the present blocker, use one strict-integer helper that rejects
   `bool` and every non-`int` JSON number at **every** comparison of a count, ceiling, or
   attempt limit. The closure report lists every application site. A pin at every site shows
   each lookalike is refused in words and the next governed command refuses before any
   session; any deliberately untreated site is named as backlog.
3. **Suites:** the implementer records one passing public and private offline suite on the
   final tree with `ResourceWarning` fatal, bytecode disabled, and the governed model's CLI
   off `PATH` (`claude` absent). The independent reviewer reruns the public suite and focused
   probes and verifies the private receipt without exposing sealed material.
4. **Implementer adversary:** before push, the implementer runs at least one isolated
   adversary pass on the closes using the blocker and authorization as its oracle. A pass
   that finds a blocker is closed and followed by another pass; stop when a pass reports
   zero blockers. Report the total count and final result. Ari remains the independent
   reviewer of record.
5. **Mutation checks:** an unmutated control passes and every non-equivalent targeted mutant
   is killed. An allowed survivor needs a mechanistic equivalence explanation and independent
   agreement. Production-code changes restart the targeted matrix. A test-only pin qualifies
   for a reduced rerun only when `git diff --numstat -- tests/` has zero deleted lines and
   every added line is inside a newly added test method; otherwise restart the matrix. A
   qualifying pin reruns the survivor, control, both suites, and any mutant not yet run on
   this candidate.
6. **Independent review:** one exact-diff review checks changed logic, reproductions,
   receipts, stated limits, and blocker rules. Peer agreement is evidence, not authority.

### 4. Stopping and change-freeze rule

When section 3 passes and no qualifying blocker remains, the reviewer issues **CLEAR at
`<exact SHA>`** and stops exploratory widening. New non-blockers enter the backlog. Any
tracked-byte change invalidates CLEAR and requires section 3 evidence—with section 3.5
deciding matrix scope—under fresh maintainer authority.

A NOT CLEAR disposition gives one minimal reproduction per blocker and returns the decision
to Skitch; it authorizes no fix. CLEAR is exact-head technical evidence only. Identity
binding and any real shard remain separate maintainer decisions. CLEAR never authorizes a
model/reviewer run, commit, push, merge, publication, release, installation, migration, or
deployment.

## Approval

- CC technical/operational review of v1.0: **pending read-only verification of the two authorized edits**
- Ari independent-review criteria: **incorporated under comments `18404556` and `18404823`**
- Skitch final approval: **Discussion #8 comment `18404823`**
