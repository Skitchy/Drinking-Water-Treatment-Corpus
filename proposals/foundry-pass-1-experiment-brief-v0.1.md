# Foundry Pass 1: Experiment Brief v0.1.2

Status: REVISED after Ari's re-review (discussions/8, 2026-08-01).
Authorized in principle by the maintainer at discussions/8 comment 17862000;
execution requires maintainer approval of this revised brief. This brief is
the implementation contract for a measured, non-production eCFR compiler
pass. It creates experimental artifacts and measurements only. Nothing in
this pass promotes generated content, alters ratified schemas, or claims
RFC 005 conformance.

## 1. Objective and claims boundary

Test whether a compiler-style pipeline can transform the existing captured
eCFR sources into promotion-ready candidate material with (a) measurable
extraction quality within the limits of available ground truth, (b)
reproducible provenance under a declared deterministic boundary, and (c) a
human review packet dispositionable in workable time. The pass earns or
kills each candidate RFC 005 promise. The only claims this experiment may
produce are measurements about itself, partitioned exactly as section 9
declares.

## 2. Sequencing and branch hygiene

The single authoritative order:

1. Brief re-review and convergence may complete now, on the board.
2. PR #7 is dispositioned and merged. The experiment does not begin, and
   this brief is not committed, on any PR #7 branch.
3. A dedicated experiment branch is cut from the resulting main. The
   converged brief lands there.
4. The maintainer dispositions the bound evaluator materials and the
   section 10 thresholds, then gives final execution authorization.
5. Only then does implementation begin.
6. All generated artifacts live under `experiments/foundry-pass-1/` on
   that branch. Read-only everywhere else: no writes to `pages/`,
   `schemas/`, `sources/`, `registry/`, `contracts/`, `tests/`, `docs/`.
7. Nothing from `experiments/` is referenced by any ratified artifact.
   Commits and pushes are the maintainer's.

## 3. Roles and channel conventions

- **Brief author and pipeline builder:** CC.
- **Independent architectural and acceptance-contract reviewer:** Ari.
  Ari also prepares the evaluator bundle (section 5), the census oracle
  (section 6), and operates the independent logical-anchor derivation
  (section 8), preserving independence from CC's parser and dependencies.
- **Maintainer:** scope, reviewer-capacity, and execution authorization;
  sets the binding time and ambiguity thresholds of section 10 before the
  graded run; dispositions reviewer projections. No compiler output
  acquires standing without the maintainer's disposition.
- **Extraction role (machine):** a fresh session with no inherited
  conversation, memory, repository access, GitHub access, web access, or
  tools beyond a recorded allowlist. It receives the input bundle of
  section 4 and nothing else. Its system prompt, task prompt, model and
  tool identities, and allowlist are recorded as digests in the run
  record.
- **Evaluator role (Ari, plus deterministic graders):** may see
  everything.

Channel conventions (Ari's five points, accepted, plus one CC addition):

1. Every conforming automated board post carries an agent marker; a marker
   proves agent origin under this protocol.
2. Absence of a marker proves only that a conforming monitor did not mark
   the object; it is not cryptographic proof of human origin.
3. Agent monitors may quote, summarize, and cite maintainer rulings; they
   never originate the authoritative record of one.
4. Consequential maintainer rulings require the maintainer-direct board
   channel or separately verifiable confirmation. A stronger signed
   mechanism must be earned by a future RFC.
5. Automation replies store their source comment ID, and consumers must
   inspect the source object itself rather than infer provenance from
   adjacency or position.
6. Any provenance or authority check binds to the specific artifact ID
   under examination; positional references are not valid check targets.
   The false hold of 2026-08-01 and its resolution are part of this
   experiment's failure record.

## 4. Fixed inputs: a closed byte manifest

The extraction role receives an assembled input bundle plus an
**evaluator-prepared input manifest** listing every permitted file by
exact path, media type, byte length, and sha256. The manifest names only:

- the 28 captured eCFR section XML files (exact filenames and digests
  from `sources/capture-manifest-2026-07-31.json`);
- the specific schema files actually required as target vocabulary, each
  by path and digest;
- the specific source-policy and authority-tier records required, each by
  path and digest;
- the ingestion-job declaration for this run.

No directories, tags, fixtures, documentation, or Git history. Bundle
identity is defined logically, not as an archive container: two bundles
are equivalent when they contain the same ordered manifest and
byte-identical member files. The bundle digest is computed over the
ordered sequence of (path, sha256) pairs in canonical JSON, recorded in
the run record. No claim of archive-level byte identity is made.

## 5. Withheld ground truth (evaluator bundle)

Evaluator-only, closed and digested in an evaluator-bundle manifest of the
same form as section 4:

- `pages/dbp.definitions.json` and `pages/dbp.mclg.json`;
- `proposals/first-proof-dbp-page-list-v0.2.md`;
- `docs/EPA_DBP_Challenge_Questions.md`;
- the census oracle (section 6);
- the probe oracles (section 8);
- any discussion-thread content describing expected page decomposition.

**Isolation probes (executable, part of every run):** the extraction role
is asked to resolve one withheld path and one out-of-manifest repository
path; both attempts must fail and the failures are recorded. A run whose
isolation probe succeeds is invalid regardless of other results.

**Oracle binding and independent disposition:** Ari authors the evaluator
materials but never self-certifies the truth set later graded against.
Before any graded output is visible, each of the following carries a
bound content digest and a maintainer or separate-reviewer disposition:
the evaluator-bundle manifest, the census oracle, every mutation and
probe oracle, the 17-page matching rubric, the challenge-question rubric,
and the metric-decision matrix of section 9a.

## 6. Census independence

The census oracle is an evaluator-only, content-addressed enumeration of
the authoritative point-in-time subpart and section universe for the
declared rule family, with the dependency-closure rule applied. It is
compiled by Ari from the authoritative source structure, reviewed by the
maintainer, and never shown to the extraction role. The compiler never
assesses the completeness of its own input list. Census completeness is
measured as compiler scope versus oracle, with omissions and exclusions
explicitly reconciled.

## 7. Reproducibility: deterministic payload boundary

Every produced record separates:

- the **deterministic transformation payload**: the canonical content;
- its **canonical byte profile**: UTF-8, LF newlines, sorted keys for
  JSON, declared XML text and entity normalization, no insignificant
  whitespace;
- its **content digest** over exactly those canonical bytes; and
- the **run/event envelope**: time, actor, environment, execution ID,
  which is class-2 attributable metadata and excluded from replay
  comparison.

Class-1 byte-identical replay applies to canonical payloads only. The
reviewer projection is a class-1 deterministic projection of recorded
class-2 candidate material, and is declared as such. The replay-coverage
record names the exact artifact IDs replayed, skipped as unchanged,
sampled, passed, and failed; counts alone are insufficient. Any class-1
replay mismatch is a build-failing defect. Per-source failure logs are
append-only with chained content-addressed log heads.

## 8. Evidence binding and anchors

- Each evidence segment binds: the complete capture digest; deterministic
  canonical-tree node selectors; normalized offsets under the declared
  normalization; and the selected canonical text digest. Raw byte ranges
  are recorded only when the represented text is actually contiguous in
  the captured bytes, and their absence is not a defect.
- The representation-bound selector is the sole authoritative binding.
  The logical citation anchor is derived metadata, re-derived by an
  **independent implementation built and operated by Ari**, sharing no
  code or dependencies with CC's derivation. Divergence between the two
  derivations is a review item, never resolved by either side alone.
  Derivation ambiguity produces a review item, never a guessed label.
  Logical-anchor equality never auto-establishes cross-release
  continuity.
- **Probe oracles are fixed before any graded run.** The
  insertion/renumbering probe carries an explicit oracle enumerating:
  selectors expected unaffected, the inserted content, the renumbered
  logical labels, the prohibited auto-continuity pairs, and the exact
  expected affected dependency set. Results report anchor survival,
  false-continuity rate, and dependency-impact precision and recall
  against that oracle.

## 9. Outputs, metrics, and partitioned claims

Outputs (all content-addressed, all under `experiments/foundry-pass-1/`):
the ingestion-job declaration; per-section capture verification records;
the canonical normalized representation with dual anchors; the quarantined
candidate bundle (quotes, claim tuples, dependencies, applicability
proposals, candidate challenge questions) with its machine-verification
report; and the reviewer projection per candidate page.

Experimental effective-time and consequence-class metadata live in the
quarantined candidate wrapper with an explicitly experimental
candidate-review payload digest. The ratified `review_payload` object
contains only `canonicalization` and `sha256`; no claim is made or implied
that v0.1 schemas model consequence classes or effective time. Reviewer
corrections to these experimental fields are measured.

### 9a. Metric-decision matrix (pre-run, bound, dispositioned)

Before the graded run, a metric-decision matrix declares, for every
reported measure: its kind (hard gate, thresholded measure, or
descriptive observation); the candidate RFC 005 promise it bears on, if
any; and the consequence of missing its threshold. Hard gates in this
brief: class-1 replay identity, isolation-probe failure, census-oracle
reconciliation, and the fail-closed probes. Thresholded measures take
their values from the maintainer's section 10 rulings. All other
measures are descriptive and may inform but never decide. Exploratory
metrics remain descriptive; the matrix exists to prevent post-hoc
interpretation, and it is itself one of the bound, dispositioned
evaluator artifacts of section 5.

Results are partitioned into exactly three claim scopes:

1. **Two-page calibration subset:** quote and structured-claim precision
   and recall against `dbp.definitions` and `dbp.mclg`, scoped to their
   sources and support.
2. **17-page decomposition comparison:** candidate page decomposition
   against the signed page plan under a matching rubric predeclared in
   the evaluator bundle.
3. **Remaining candidate material:** deterministic validity, review
   disposition outcomes, and observed corrections only. No ground-truth
   accuracy claim.

Candidate challenge questions are graded against a predeclared rubric:
source answerability, traceability to captured text, duplicate rate, and
concept coverage relative to the 40-question bank as a coverage reference,
not as an answer key.

Provenance metrics: 100% of class-1 payloads replay byte-identical; the
replay-coverage record is complete by artifact ID.

Git operational measurements, recorded at baseline and post-experiment
with no threshold or migration implied: clean-clone bytes and time,
incremental-fetch bytes and time after the experiment tranche, CI checkout
time, pack/repack behavior, largest-file and host-limit margins, and
offline verification time from a clean clone.

## 10. Human factors: honest statistics

Measured on the maintainer's disposition of reviewer projections:

- every disposition duration is reported individually, with median and
  maximum; a p95 is reported only if the sample reaches 20 dispositions,
  otherwise any interpolated percentile is labeled descriptive with no
  pass/fail force;
- machine-proposal acceptance, correction, and rejection rates;
- defect escape reported as "zero observed in N fixed adversarial
  checks," with N stated, never as a zero defect rate;
- unresolved-ambiguity count per packet;
- binding thresholds for workable review time and ambiguity limits are
  set by the maintainer before the graded run, after seeing measurement
  cost but before seeing graded outcomes (queued maintainer item).

**WIP definition and enforcement:** work in progress equals candidate
pages produced but not dispositioned, regardless of display. The pipeline
emits candidate pages in batches whose size cannot push WIP past five;
production pauses at the cap. Backlog never weakens a gate; batch approval
does not exist.

## 11. Probes and stopping semantics

Probes per run: clean rerun (class-1 payload identity); insertion and
renumbering mutation (against its fixed oracle); substantive table-cell
edit (semantic diff and impact, precision and recall against the mutation
oracle); omitted-section census defect (input list reduced, census oracle
unchanged, omission must be flagged); corrupted capture (one byte altered;
the affected stage fails closed and nothing downstream emits); isolation
probes (section 5); independent-lineage disagreement on a subset
preselected by a recorded seed rule before any outputs exist, with model
lineage, prompts, configuration, and tools recorded; agreement is triage
evidence only.

Expected probe failures are successes and are reported as fail-closed
verifications, separately from unexpected stops. Unexpected stopping
conditions, each a pause-for-diagnosis rather than a conclusion: a capture
digest failure outside the corruption probe; any class-1 replay mismatch;
inability to generate a reviewer projection; unresolved ambiguities
exceeding the provisional threshold of 10 per section (provisional,
diagnostic, carries no design verdict); WIP cap breach. Stopping is a
result, not a failure of the experiment.

## 12. Prohibitions

No promotion of generated content. No ratified-schema changes. No RFC 005
conformance claims. No public claims derived from this pass except the
partitioned measurements themselves, dispositioned through review.

## 13. Disposition path

Identical to the section 2 order, restated: brief convergence on the
board; PR #7 merges; experiment branch cut from main and the converged
brief committed there; maintainer dispositions the bound evaluator
materials and section 10 thresholds and gives final execution
authorization; implementation begins; outputs and measurements post to
discussions/8; results feed the RFC 005 draft, which follows the
experiment.

## 14. Revision history

- **v0.1 (2026-08-01):** initial draft.
- **v0.1.1 (2026-08-01):** all nine findings of Ari's adversarial review
  adopted: PR #7 separation and dedicated branch; closed byte manifests
  for input and evaluator bundles; fresh-session isolation with
  executable isolation probes and digested prompts/allowlist;
  evaluator-compiled census oracle with maintainer review; deterministic
  payload versus run-envelope boundary with declared canonical byte
  profile and artifact-ID replay coverage; corrected XML evidence binding
  with contiguity-conditional raw ranges; Ari-operated independent
  logical-anchor derivation; fixed probe oracles with false-continuity
  and precision/recall reporting; evaluation claims partitioned into
  three scopes with a challenge-question rubric; honest small-sample
  statistics and maintainer-set thresholds; executable WIP definition and
  probe-failure semantics; Git operational measurements; experimental
  effective-time and consequence metadata quarantined with no v0.1
  schema claim.
- **v0.1.2 (2026-08-01):** Ari's four re-review precision fixes adopted:
  bundle identity defined as the logical file set (ordered manifest plus
  member digests), no archive-byte claim; every evaluator oracle
  content-bound and dispositioned by the maintainer or a separate
  reviewer before graded output exists; pre-run metric-decision matrix
  (section 9a) naming each measure hard gate, thresholded, or
  descriptive; single authoritative sequencing stated identically in
  sections 2 and 13.
