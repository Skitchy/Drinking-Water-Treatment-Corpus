# Foundry Pass 2: Experiment Brief v0.4 (the release gate)

Status: DRAFT v0.4 for convergence on discussion #8, then a fresh content-bound maintainer ratification. Supersedes v0.3 (ratified 18176893; superseded before any reviewer ran, per Ari's 2026-08-27 review, discussioncomment-18177749) and the Pass 2 proposal draft (proposals/foundry-pass-2-release-gate-draft.md, posted as discussioncomment-18171737). Incorporates Ari's six precision controls (discussioncomment-18171955), Ari's three v0.2 amendments and scope guard (discussioncomment-18172200), and the maintainer's two rulings, both confirmed maintainer-direct on the board: (a) the maintainer is not the per-packet bottleneck (18171771); (b) the release universe for Pass 2 is claims and evidence only (18172107).

Pass 1 brief v0.1.2 remains in force for every section not amended here. Section numbers below refer to the Pass 1 brief where a section is amended; new sections are marked NEW.

## 1. Objective and claims boundary (amended)

Pass 2 tests one hypothesis: fail-closed, independently produced machine unanimity can move the human out of the per-claim loop without silently weakening the release boundary.

What Pass 2 does NOT claim: that machine agreement replaces consequence-sensitive human judgment in production; that a machine-unanimous claim is a human-reviewed claim; RFC 005 conformance; standing for any generated content outside the experimental release candidate defined in section 9.

Pass 2 produces measurements and, if the gates of section 9 pass, one experimental release candidate whose every claim is labeled machine-unanimous.

## 1a. Release universe: claims and evidence only (NEW, maintainer ruling 2026-08-26)

The release-eligible semantic unit for Pass 2 is the **claim-and-evidence record**: one canonical claim payload (subject, relation, value, unit, conditions, applicability, effective-time fields, dependencies, all as emitted by the Pass 1 canonical representation) plus its normalized support-anchor set and the byte-verified quote selections those anchors bind.

Explicitly OUTSIDE the release universe and acquiring no standing in Pass 2: page proposals (178 in the clean Pass 1 run), page membership and boundaries, dependency assemblies between pages, and challenge questions (189). Declared ambiguities (88) are review inputs, not release objects. A claim that references a page acquires standing only for the claim; the page it points into acquires none. Page-level review is a separate experiment with its own brief.

## 2. Sequencing (amended)

1. This brief converges on discussion #8 (Ari's review, CC's revisions, in this order until neither side has an open control).
2. Ari authors the isolated reviewer contract (section 3a) and the mixed sealed control oracle (section 5a), delivered with content digests before any reviewer runs.
3. Maintainer ratifies the exact converged brief and the bound evaluator identities by digest, on the board, maintainer-direct channel.
4. CC implements: adapter/engine boundary (section 7a), review-input bundle emitter, disposition records, unanimity merge, partition reconciliation, release report. No engine code before the boundary is drawn in the tree (maintainer goal ruling 2026-08-26: the tool that ingests any subject matter is the product; the dataset is proof of work).
5. Measured run on the existing clean Pass 1 outputs (git 4574c8f). Outputs and measurements post to discussion #8.
6. Maintainer dispositions the release report (section 6a) and reports the time it took.

Commits remain the maintainer's. Working files stay in the experiment branch.

## 3. Roles (amended)

- **Pipeline builder:** CC. The builder emits the review-input bundle and runs the merge; the builder does not review.
- **Reviewer A (CC lineage):** a fresh, isolated role session per section 3a, operated by CC's harness, NOT an interactive CC session and NOT the extraction role's session or lineage context. If Reviewer A cannot be shown independent of the extraction role by the section 3a record, its output is labeled author-side re-review and does not count toward unanimity; in that case the experiment narrows to one independent review (Reviewer B) plus an author-side re-review, and says so.
- **Reviewer B (Ari lineage):** a fresh isolated role operated on Ari's side, per Ari's own statement; never an inherited-context session.
- **Evaluator (Ari plus deterministic graders):** authors the sealed control oracle; may see everything after graded outputs are fixed.
- **Maintainer:** ratifies the brief and bound identities; dispositions the release report once per release; sets the release-review duration threshold of section 6a before graded reviewer outcomes are visible.

Neither reviewer adjudicates the other. Nobody resolves a disagreement; exclusion is the resolution.

## 3a. Independence as an executable isolation contract (NEW, Ari control 3)

Both reviewers run from the same content-bound **review-input bundle**: the frozen review universe of section 4a, the canonical source bytes and anchors those records bind, the review task prompt, and nothing else. The bundle digest is recorded before either reviewer runs.

Neither reviewer can see: the other reviewer's output; discussion history or any prior human disposition (including packet-141.130's checkbox); evaluator ground truth or the identities of sealed controls; inherited project, session, memory, or identity context. Concretely for CC-side sessions: the isolation trio (CC_ANCHOR_BYPASS_ROLE_SESSION=1, --setting-sources project, --strict-mcp-config) plus a recorded tool allowlist, plus a leak probe run BEFORE the first real review whose transcript is part of the run record. A failed leak probe invalidates the run before it starts.

Recorded as digests per reviewer: system prompt, task prompt, model lineage and version, parser version, tool allowlist, settings sources, configuration. Ari's reviewer contract specifies the same record for Reviewer B. The gate validates every mechanically checkable identity field against the bound artifact it names (prompt, template, schema, harness, probe transcript); operator and model lineage remain attestations. Each reviewer also delivers a content-addressed run-record manifest covering the probe transcript, the identity record, every shard run record, every fixed output, and any failed-session evidence; both manifests are bound through the report into the release manifest.

## 4. Fixed inputs (amended)

The closed byte manifest of Pass 1 section 4 is unchanged. Pass 2 adds the clean Pass 1 output tree at git 4574c8f as a fixed input, digested as a whole and per record.

## 4a. Frozen review universe and the deterministic partition (NEW, Ari control 4)

Two universes, defined separately (Ari amendment 2). The **natural release universe** is every release-eligible claim-and-evidence record from the fixed Pass 1 outputs, by artifact ID. The **review universe** is the disjoint union of the natural release universe and the sealed controls of section 5a, interleaved indistinguishably. Before either reviewer runs, the builder emits `out/review-universe.json` listing the review universe with a digest over the whole; the natural release universe is listed separately, under seal until grading, with its own digest. Both are frozen at those digests; nothing enters or leaves afterward. Because the fixed natural Pass 1 outputs are public, a public mixed universe would let anyone derive the controls by subtraction; therefore the mixed review universe, the shards, the sealed natural listing, and the control-record bundle stay outside public git until both reviewer outputs are content-bound and fixed. Pre-run public evidence is commitments and digests only (`out/review-input-bundle.json`); the complete evidence bundle is published after outputs are fixed.

After merge, the release report must reconcile exactly:

`all eligible inputs = unanimously accepted + excluded by reason + review-execution failures`

Every review input is partitioned exactly once: the three sets are disjoint, list artifact IDs completely, and their counts sum to the review-universe count. After grading, every control is removed before the release projection is constructed; controls count toward NONE of the section gate, the acceptance gate, concept coverage, or released-claim totals. The denominators of every gate in section 9 are the natural release universe only. Excluded-by-reason carries one reason code per record: correction proposed, payload non-equivalent, anchor mismatch, rejected by A, rejected by B, rejected by both, abstention, missing disposition. Any record that appears in the universe and in none of the three sets, or in more than one, is a partition mismatch and a hard stop. Coverage is reported per source section for the natural release universe (the 38 sections) and, after reveal, against the evaluator-held 40-question concept-reference bank. Concept-reference coverage is evaluator grading, not an engine-emitted list, and is not a release gate unless separately precommitted.

## 5. Withheld ground truth (amended)

The Pass 1 evaluator bundle and census oracle stand. Pass 2 adds the mixed sealed control oracle of section 5a, authored by Ari, committed by digest before execution.

## 5a. Mixed sealed controls (NEW, Ari control 5)

The sealed control set contains BOTH deliberately wrong claims AND independently certified correct claims, indistinguishable from real records inside the review-input bundle. Wrong controls are stratified across the error classes that matter: numeric or unit substitution, negation, dropped qualifier, applicability error, cross-reference error, wrong anchor or context, condition or effective-time distortion. Correct controls are certified by the evaluator against source bytes before sealing.

Precommitted before execution: the complete oracle (which control is which), the count per stratum, and the thresholds. Hard stops: any planted wrong claim unanimously accepted; positive-control acceptance below the precommitted floor (a reject-all or pathologically over-excluding reviewer cannot be scored as a pass). Controls are removed from the release candidate after grading and reported separately; they never acquire standing.

## 6. Unanimity binds the canonical payload (NEW, Ari control 2)

A record is unanimously accepted only when both reviewers return `accept` over the SAME canonical review-payload digest AND the same normalized support-anchor set. The payload digest covers the full claim payload of section 1a (subject, relation, value, unit, conditions, applicability, effective-time fields, dependencies), so two reviewers citing the same paragraph while meaning different values cannot agree by accident.

Everything else goes to the excluded set with its reason code: any correction from either side, any non-equivalent payload, any anchor mismatch, either reviewer's rejection, abstention, execution failure, missing disposition. Excluded records are listed in full in the report appendix with both reviewers' outputs side by side. They are not resolved in Pass 2.

## 6a. The maintainer signature and the bounded report (NEW, Ari control 6)

The maintainer signs once per release. The signature attests exactly this: the bound process ran under the ratified brief; the hard gates of sections 4a and 5a passed; the coverage and exclusions were read and understood; the experimental release candidate is accepted as a whole. It does NOT attest per-claim human review. Every accepted claim's provenance is labeled `machine-unanimous` with both reviewer digests; nothing in the corpus may relabel it human-reviewed by implication.

The signature names exactly one **release-manifest digest** (Ari amendment 3). The release manifest transitively binds, by content digest: the ratified brief; the review-input bundle and both universe listings; both reviewers' identity/configuration records and their complete outputs; the partition, the report, and its appendices; the control-grading record; and the exact experimental release candidate. A signature over a manifest digest cannot float across regenerated artifacts; any regeneration produces a new manifest that needs a new signature.

Report shape: main body = decision summary, gate results, coverage per source section and evaluator-graded concept-reference coverage after reveal, the partition counts, and risk-ranked exceptions (excluded records grouped by reason, worst first). Appendices, content-bound by digest and available for drill-down: the complete disagreement and exclusion records, both reviewers' full outputs, the control grading, the run record.

Bound BEFORE graded reviewer outcomes are visible, AFTER the report template exists: a release-review duration threshold set by the maintainer, and the consequence of missing it (the Pass 1 section 10 discipline, moved from packet to release). Otherwise Pass 2 moves the bottleneck into one large report and declares victory.

## 7. Reproducibility (unchanged)

Class-1 replay identity applies to the review-input bundle, the merge, and the report: same universe digest plus same reviewer outputs must reproduce the same partition and report bytes.

## 7a. Adapter/engine boundary (NEW, maintainer goal ruling 2026-08-26)

Implementation draws one boundary in the tree before engine work: **source adapters in front, one subject-agnostic engine behind.** An adapter hands the engine a fixed contract: source bytes with digests, a unit tree (sections or their equivalent), and the anchor rules for that source type. The engine promises back the same objects for any source: canonical claim-and-evidence records, verification records, the review universe, the partition, the release report. eCFR is adapter #1. The engine must not import anything eCFR-specific. Scope guard (Ari): Pass 2 draws and exercises only the minimum adapter/engine interface needed to consume the fixed Pass 1 outputs; it does not build the PDF or Word adapters, does not regenerate the fixed Pass 1 extraction, and is not a general refactor. A second adapter (PDF manual, then Word) is a later pass with its own brief; its known design constraint is recorded now so the engine contract leaves room for it: scanned PDFs have no text bytes, so quote binding there will run through an OCR-layer digest derived from a page-image digest, one extra custody link, stated as such.

## 8. Evidence binding (unchanged)

Dual anchors and byte-exact quote verification stand. Pass 2 adds: the normalized support-anchor set is part of the unanimity test (section 6).

## 9. Outputs, metrics, and gates (amended)

Hard gates (any failure = no release candidate, measured failed attempt only): partition reconciliation (4a); no planted wrong claim unanimously accepted (5a); positive-control floor met (5a); leak probes clean for both reviewers (3a); BOTH reviewers satisfy the independence contract of section 3a (Ari amendment 1: if either reviewer fails it, including Reviewer A downgrading to author-side re-review, the run is a measured failed attempt only; the downgraded output may be reported as descriptive evidence but no experimental release candidate may issue); class-1 replay of merge and report (7).

Coverage gate for an experimental release candidate (precommitted here, accepted by Ari as first-pass EXPERIMENTAL gates; maintainer may tighten at ratification; they do not establish corpus completeness): unanimous acceptance covers at least 30 of 38 sections with at least one accepted natural claim each, AND total unanimous acceptance is at least 50 percent of the natural release universe (controls excluded from both numerator and denominator per 4a). Below either number, the run is a measured failed attempt and posts as such; the report still ships for the record.

Honest statistics (section 10 moved to release scope): inter-reviewer agreement rate per section; excluded-by-reason counts; control grading by stratum, reported as "zero planted errors accepted in N controls" with N stated, never as an error rate; per-reviewer abstention and execution-failure counts; release-review duration reported individually per release; the coverage figures of 4a.

Partitioned claims: Pass 2 may claim only what these measurements show about THIS universe under THIS contract. No production claim.

## 10. Prohibitions (amended)

Pass 1 section 12 stands: no promotion of generated content; no ratified-schema changes; no RFC 005 conformance claims; no public claims beyond the partitioned measurements. Added: no reviewer adjudicates the other; no human disposition enters the review inputs; no record leaves the universe between emission and report.

## 11. Disposition path (amended)

Converge here; Ari delivers reviewer contract and control oracle by digest; maintainer ratifies the exact brief and bound identities (maintainer-direct channel, artifact-ID-bound); CC implements per section 2; measured run; report posted; maintainer dispositions the release report once and reports the duration; results feed the RFC 005 draft.

## 12. Revision history

- v0.4 (2026-08-27, CC, DRAFT): after Ari's fresh-instance review of the built pipeline (18177749). Section 4a: mixed review universe and controls private until outputs are fixed; concept-reference coverage is evaluator-graded, not an engine list (the v0.2 phrase "concept list from the Pass 1 canonical index" named nothing that exists). Section 6a: report wording to match. Section 3a: mechanical identity validation and run-record manifests bound into the release manifest. Controls and sealed oracle regenerated by Ari outside public git (v0.1 identities public by design, treated as burned). Requires a fresh ratification over the new brief, evaluator identities, commitments, oracle, and thresholds.

- v0.3 (2026-08-27, CC): Ari's three v0.2 amendments applied (18172200): independence loss is a hard gate with no release candidate (section 9); review universe and natural release universe defined separately, controls excluded from every gate denominator (sections 4a and 9); maintainer signature bound to one release-manifest digest (section 6a); section 7a scope guard. Maintainer's claims-and-evidence-only ruling confirmed on the board (18172107).

- v0.2 (2026-08-26, CC): first Pass 2 brief. From the release-gate proposal (18171737) plus Ari's six controls (18171955) and the maintainer's two rulings (18171771 direction; claims-and-evidence-only, in session, to be confirmed on the board).
