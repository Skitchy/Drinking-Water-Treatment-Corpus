import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");
const evaluationTime = new Date("2026-07-29T00:00:00Z");

function load(relativePath) {
  return JSON.parse(fs.readFileSync(path.join(root, relativePath), "utf8"));
}

function sha256File(relativePath) {
  return createHash("sha256")
    .update(fs.readFileSync(path.join(root, relativePath)))
    .digest("hex");
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function expectFailure(fn, message) {
  let failed = false;
  try {
    fn();
  } catch {
    failed = true;
  }
  assert(failed, message);
}

function uniqueBy(items, key, label) {
  const values = items.map((item) => item[key]);
  assert(
    new Set(values).size === values.length,
    `${label} contains a duplicate ${key}`
  );
}

function parseTime(value, label) {
  const parsed = new Date(value);
  assert(!Number.isNaN(parsed.valueOf()), `${label} is not a valid timestamp`);
  return parsed;
}

function parseDate(value, label) {
  return parseTime(`${value}T00:00:00Z`, label);
}

const schemaPaths = [
  "schemas/drinking-water-profile-v0.1.schema.json",
  "schemas/reviewer-registry-v0.1.schema.json",
  "schemas/source-registry-v0.1.schema.json",
  "schemas/corpus-release-manifest-v0.1.schema.json",
  "schemas/runtime-assurance-manifest-v0.1.schema.json",
  "schemas/verified-answer-v0.1.schema.json",
  "schemas/audit-envelope-v0.1.schema.json"
];

const ajv = new Ajv2020({
  allErrors: true,
  strict: true
});
addFormats(ajv);

for (const schemaPath of schemaPaths) {
  const schema = load(schemaPath);
  assert(
    schema.$schema === "https://json-schema.org/draft/2020-12/schema",
    `${schemaPath} must declare JSON Schema 2020-12`
  );
  assert(
    schema.$id?.startsWith("urn:dwtc:schema:"),
    `${schemaPath} must use an immutable logical $id`
  );
  ajv.addSchema(schema);
}

function validateWith(schemaId, value, label) {
  const validate = ajv.getSchema(schemaId);
  assert(validate, `Schema ${schemaId} was not registered`);
  if (!validate(value)) {
    throw new Error(
      `${label} failed ${schemaId}: ${ajv.errorsText(validate.errors, {
        separator: "; "
      })}`
    );
  }
}

const schemaIds = {
  profile: "urn:dwtc:schema:drinking-water-profile:v0.1",
  reviewer: "urn:dwtc:schema:reviewer-registry:v0.1",
  source: "urn:dwtc:schema:source-registry:v0.1",
  corpus: "urn:dwtc:schema:corpus-release-manifest:v0.1",
  runtime: "urn:dwtc:schema:runtime-assurance-manifest:v0.1",
  answer: "urn:dwtc:schema:verified-answer:v0.1",
  audit: "urn:dwtc:schema:audit-envelope:v0.1"
};

const manifest = load("tests/acceptance/manifest-v0.1.json");
const expectedCaseIds = Array.from(
  { length: 40 },
  (_, index) => `AT-${String(index + 1).padStart(3, "0")}`
);
assert(
  JSON.stringify(manifest.cases.map((testCase) => testCase.id)) ===
    JSON.stringify(expectedCaseIds),
  "Acceptance manifest must contain AT-001 through AT-040 in order"
);
for (const testCase of manifest.cases) {
  for (const artifact of testCase.artifacts) {
    assert(
      fs.existsSync(path.join(root, artifact)),
      `${testCase.id} references missing artifact ${artifact}`
    );
  }
}

const registry = load(
  "tests/acceptance/fixtures/reviewer-registry-valid.json"
);
const sourceRegistry = load(
  "tests/acceptance/fixtures/source-registry-valid.json"
);
const validProfile = load("tests/acceptance/fixtures/profile-valid.json");
const invalidProfile = load(
  "tests/acceptance/fixtures/profile-invalid-review-hash.json"
);
const corpus = load(
  "tests/acceptance/fixtures/corpus-release-manifest-valid.json"
);
const runtime = load(
  "tests/acceptance/fixtures/runtime-assurance-manifest-valid.json"
);
const baselinePath = "contracts/assurance-check-baseline-v0.1.json";
const requiredCheckBaseline = load(baselinePath);
const requiredCheckBaselineSha256 = sha256File(baselinePath);
const evidenceBacked = load(
  "tests/acceptance/fixtures/answer-valid-evidence-backed.json"
);
const evidenceOnly = load(
  "tests/acceptance/fixtures/answer-valid-evidence-only.json"
);
const abstention = load(
  "tests/acceptance/fixtures/answer-valid-abstention.json"
);
const audit = load("tests/acceptance/fixtures/audit-envelope-valid.json");
const mutations = load(
  "tests/acceptance/fixtures/artifact-mutations-v0.1.json"
);

validateWith(schemaIds.reviewer, registry, "Reviewer registry fixture");
validateWith(schemaIds.source, sourceRegistry, "Source registry fixture");
validateWith(schemaIds.profile, validProfile, "Profile fixture");
validateWith(schemaIds.profile, invalidProfile, "Invalid semantic profile");
validateWith(schemaIds.corpus, corpus, "Corpus manifest fixture");
validateWith(schemaIds.runtime, runtime, "Runtime manifest fixture");
validateWith(schemaIds.answer, evidenceBacked, "Evidence-backed fixture");
validateWith(schemaIds.answer, evidenceOnly, "Evidence-only fixture");
validateWith(schemaIds.answer, abstention, "Abstention fixture");
validateWith(schemaIds.audit, audit, "Audit fixture");
uniqueBy(registry.reviewers, "reviewer_id", "Reviewer registry");

assert(
  requiredCheckBaseline.schema_version ===
    "assurance-check-baseline/v0.1",
  "Required-check baseline has an unknown schema version"
);
assert(
  requiredCheckBaseline.artifact_id ===
    "assurance-check-baseline/v0.1",
  "Required-check baseline has an unknown artifact ID"
);
assert(
  requiredCheckBaseline.digest_scope === "exact-utf8-file-bytes",
  "Required-check baseline must define its digest scope"
);
const baselineShapeProbe = structuredClone(runtime);
baselineShapeProbe.required_checks = requiredCheckBaseline.required_checks;
validateWith(
  schemaIds.runtime,
  baselineShapeProbe,
  "Required-check baseline rule shape"
);

function requiredRuleKey(rule) {
  return `${rule.outcome}:${rule.subject_kind}:${rule.claim_kind ?? "*"}`;
}

function validateRuntimeManifestSemantics(candidateRuntime) {
  assert(
    candidateRuntime.required_check_baseline.artifact_id ===
      requiredCheckBaseline.artifact_id,
    "Runtime manifest names an unknown required-check baseline"
  );
  assert(
    candidateRuntime.required_check_baseline.sha256 ===
      requiredCheckBaselineSha256,
    "Runtime manifest required-check baseline digest mismatch"
  );
  uniqueBy(
    candidateRuntime.required_checks.map((rule) => ({
      key: requiredRuleKey(rule)
    })),
    "key",
    "Runtime required-check rules"
  );
  const ruleByKey = new Map(
    candidateRuntime.required_checks.map((rule) => [
      requiredRuleKey(rule),
      rule
    ])
  );
  for (const baseline of requiredCheckBaseline.required_checks) {
    const rule = ruleByKey.get(requiredRuleKey(baseline));
    assert(
      rule,
      `Runtime manifest omits baseline rule ${requiredRuleKey(baseline)}`
    );
    for (const checkId of baseline.check_ids) {
      assert(
        rule.check_ids.includes(checkId),
        `Runtime rule ${requiredRuleKey(baseline)} omits baseline check ${checkId}`
      );
    }
  }
}

validateRuntimeManifestSemantics(runtime);

function reviewerForEvent(reviewerId, scope, at, candidateRegistry = registry) {
  const reviewer = candidateRegistry.reviewers.find(
    (entry) => entry.reviewer_id === reviewerId
  );
  assert(reviewer, `Unknown reviewer ${reviewerId}`);
  assert(
    reviewer.review_scopes.includes(scope),
    `Reviewer ${reviewerId} lacks scope ${scope}`
  );
  const eventTime = parseTime(at, `Review event ${reviewerId}`);
  const authorizedFrom = parseTime(
    reviewer.authorized_from,
    `Reviewer authorized_from ${reviewerId}`
  );
  const authorizedThrough = reviewer.authorized_through
    ? parseTime(
        reviewer.authorized_through,
        `Reviewer authorized_through ${reviewerId}`
      )
    : null;
  assert(
    eventTime >= authorizedFrom &&
      (!authorizedThrough || eventTime <= authorizedThrough),
    `Reviewer ${reviewerId} was outside the authorization interval at ${at}`
  );
  const qualifying = reviewer.qualifications.some((qualification) => {
    const validFrom = parseDate(
      qualification.valid_from,
      `Qualification valid_from for ${reviewerId}`
    );
    const expiresAt = qualification.expires_at
      ? parseDate(
          qualification.expires_at,
          `Qualification expires_at for ${reviewerId}`
        )
      : null;
    return eventTime >= validFrom && (!expiresAt || eventTime <= expiresAt);
  });
  assert(
    qualifying,
    `Reviewer ${reviewerId} lacked a valid qualification at ${at}`
  );
  if (
    reviewer.status === "revoked" &&
    reviewer.revocation?.invalidates_prior_reviews
  ) {
    const effectiveAt = parseTime(
      reviewer.revocation.effective_at,
      `Reviewer revocation ${reviewerId}`
    );
    assert(
      eventTime < effectiveAt,
      `Review by ${reviewerId} is invalidated by revocation`
    );
  }
  return reviewer;
}

function validateSourceRegistrySemantics(candidateRegistry) {
  uniqueBy(candidateRegistry.sources, "source_id", "Source registry");
  uniqueBy(
    candidateRegistry.sources.map((source) => source.reproduction_decision),
    "decision_id",
    "Source registry"
  );
  for (const source of candidateRegistry.sources) {
    const decision = source.reproduction_decision;
    assert(
      decision.status === "approved",
      `Source ${source.source_id} lacks an approved reproduction decision`
    );
    reviewerForEvent(decision.reviewed_by, "licensing", decision.reviewed_at);
  }
}

function validatePopulation(applicability, label) {
  const population = applicability.population;
  if (
    population &&
    population.minimum !== undefined &&
    population.maximum !== undefined
  ) {
    assert(
      population.minimum <= population.maximum,
      `${label} population minimum exceeds maximum`
    );
  }
}

function rejectDerivationCycles(claims) {
  const graph = new Map(
    claims
      .filter((claim) => claim.kind === "derived")
      .map((claim) => [claim.claim_id, claim.derivation.input_claim_ids])
  );
  const visiting = new Set();
  const visited = new Set();

  function visit(claimId) {
    if (visited.has(claimId)) return;
    assert(!visiting.has(claimId), `Derived claim cycle includes ${claimId}`);
    visiting.add(claimId);
    for (const inputId of graph.get(claimId) ?? []) {
      if (graph.has(inputId)) visit(inputId);
    }
    visiting.delete(claimId);
    visited.add(claimId);
  }

  for (const claimId of graph.keys()) visit(claimId);
}

function validateTableClaim(claim) {
  const table = claim.table_value;
  assert(
    table.row_dimension.dimension_id !==
      table.column_dimension.dimension_id,
    `Table claim ${claim.claim_id} reuses a dimension ID`
  );
  function endsBefore(left, right) {
    if (left.maximum === undefined || right.minimum === undefined) {
      return false;
    }
    if (left.maximum < right.minimum) return true;
    if (left.maximum > right.minimum) return false;
    return !(left.maximum_inclusive && right.minimum_inclusive);
  }
  for (const dimension of [table.row_dimension, table.column_dimension]) {
    uniqueBy(
      dimension.bands,
      "band_id",
      `Table claim ${claim.claim_id} dimension ${dimension.name}`
    );
    for (const band of dimension.bands) {
      if (band.minimum !== undefined && band.maximum !== undefined) {
        assert(
          band.minimum <= band.maximum,
          `Table claim ${claim.claim_id} band ${band.band_id} has minimum > maximum`
        );
        if (band.minimum === band.maximum) {
          assert(
            band.minimum_inclusive && band.maximum_inclusive,
            `Table claim ${claim.claim_id} band ${band.band_id} is an empty range`
          );
        }
      }
    }
    for (let leftIndex = 0; leftIndex < dimension.bands.length; leftIndex += 1) {
      for (
        let rightIndex = leftIndex + 1;
        rightIndex < dimension.bands.length;
        rightIndex += 1
      ) {
        const left = dimension.bands[leftIndex];
        const right = dimension.bands[rightIndex];
        assert(
          endsBefore(left, right) || endsBefore(right, left),
          `Table claim ${claim.claim_id} has overlapping bands ${left.band_id} and ${right.band_id}`
        );
      }
    }
  }
  const rowBandIds = new Set(
    table.row_dimension.bands.map((band) => band.band_id)
  );
  const columnBandIds = new Set(
    table.column_dimension.bands.map((band) => band.band_id)
  );
  uniqueBy(table.cells, "cell_id", `Table claim ${claim.claim_id} cells`);
  const seenCells = new Set();
  for (const cell of table.cells) {
    assert(
      rowBandIds.has(cell.row_band),
      `Table claim ${claim.claim_id} cell references unknown row band ${cell.row_band}`
    );
    assert(
      columnBandIds.has(cell.column_band),
      `Table claim ${claim.claim_id} cell references unknown column band ${cell.column_band}`
    );
    const cellKey = `${cell.row_band}:${cell.column_band}`;
    assert(
      !seenCells.has(cellKey),
      `Table claim ${claim.claim_id} has duplicate cell ${cellKey}`
    );
    seenCells.add(cellKey);
  }
  assert(
    seenCells.size === rowBandIds.size * columnBandIds.size,
    `Table claim ${claim.claim_id} does not cover every row-band and column-band combination`
  );
}

function validateProfileSemantics(profile, candidateSourceRegistry) {
  const payloadDigest = profile.review_payload.sha256;
  assert(profile.verified.length > 0, "Profile has no verification events");
  for (const event of profile.verified) {
    assert(
      event.review_payload_sha256 === payloadDigest,
      `Verification by ${event.by} is bound to a different review payload`
    );
    if (event.actor_type === "human") {
      for (const scope of event.scopes) {
        reviewerForEvent(event.by, scope, event.at);
      }
    }
  }

  if (profile.status === "stable") {
    assert(
      profile.source_watch.last_result === "unchanged",
      "Stable page has a non-unchanged source-watch result"
    );
    assert(
      evaluationTime <
        parseTime(profile.source_watch.next_due_at, "source_watch.next_due_at"),
      "Stable page source watch is overdue at evaluation time"
    );
    assert(
      evaluationTime <= parseDate(profile.stale_after, "stale_after"),
      "Stable page is stale at evaluation time"
    );
  }

  uniqueBy(profile.source_refs, "source_id", "Profile source references");
  uniqueBy(profile.quotes, "quote_id", "Profile quotes");
  uniqueBy(profile.claims, "claim_id", "Profile claims");

  const sourceById = new Map(
    candidateSourceRegistry.sources.map((source) => [source.source_id, source])
  );
  for (const reference of profile.source_refs) {
    const source = sourceById.get(reference.source_id);
    assert(source, `Unknown source ${reference.source_id}`);
    assert(
      source.captured_sha256 === reference.captured_sha256,
      `Captured-source digest mismatch for ${reference.source_id}`
    );
    assert(
      source.reproduction_decision.status === "approved",
      `Source ${reference.source_id} is not approved for reproduction`
    );
    assert(
      source.reproduction_decision.decision_payload_sha256 ===
        reference.licensing_decision_payload_sha256,
      `Licensing-decision digest mismatch for ${reference.source_id}`
    );
  }

  const sourceReferenceIds = new Set(
    profile.source_refs.map((reference) => reference.source_id)
  );
  for (const quote of profile.quotes) {
    assert(
      sourceReferenceIds.has(quote.source_id),
      `Quote ${quote.quote_id} references an undeclared source`
    );
    const source = sourceById.get(quote.source_id);
    assert(
      quote.captured_source_sha256 === source.captured_sha256,
      `Quote ${quote.quote_id} is bound to a different source snapshot`
    );
  }

  const quoteIds = new Set(profile.quotes.map((quote) => quote.quote_id));
  validatePopulation(profile.applicability, "Page");
  for (const claim of profile.claims) {
    validatePopulation(claim.applicability, `Claim ${claim.claim_id}`);
    for (const quoteId of claim.supporting_quote_ids) {
      assert(
        quoteIds.has(quoteId),
        `Claim ${claim.claim_id} references unknown quote ${quoteId}`
      );
    }
    if (claim.kind === "table") {
      validateTableClaim(claim);
    }
    if (claim.kind === "derived") {
      assert(
        runtime.algorithm_registry.algorithm_ids.includes(
          claim.derivation.algorithm_id
        ),
        `Derived claim ${claim.claim_id} uses an unregistered algorithm`
      );
    }
  }
  rejectDerivationCycles(profile.claims);
}

validateSourceRegistrySemantics(sourceRegistry);
validateProfileSemantics(validProfile, sourceRegistry);
expectFailure(
  () => validateProfileSemantics(invalidProfile, sourceRegistry),
  "AT-001 fixture must fail review-payload binding"
);

function subjectKey(subject) {
  return `${subject.kind}:${subject.id}`;
}

function checkCovers(answer, checkId, subject, requirePass) {
  return answer.checks.some(
    (check) =>
      check.check_id === checkId &&
      (!requirePass || check.verdict === "pass") &&
      check.subjects.some((candidate) => subjectKey(candidate) === subjectKey(subject))
  );
}

function claimCellSubjectId(claimId, cellId) {
  return `${claimId}#${cellId}`;
}

function expectedSubjects(
  answer,
  subjectKind,
  claimKind,
  candidateProfile
) {
  if (subjectKind === "envelope") {
    return [
      {
        kind: "envelope",
        id: answer.answer_id
      }
    ];
  }
  if (subjectKind === "page") {
    const pageIds = [
      ...answer.claim_refs.map((reference) => reference.page_id),
      ...answer.quote_refs.map((reference) => reference.page_id)
    ];
    return [...new Set(pageIds)].map((id) => ({ kind: "page", id }));
  }
  if (subjectKind === "quote") {
    return answer.quote_refs.map((reference) => ({
      kind: "quote",
      id: reference.quote_id
    }));
  }
  const claimById = new Map(
    candidateProfile.claims.map((claim) => [claim.claim_id, claim])
  );
  if (subjectKind === "claim-cell") {
    return answer.claim_refs.flatMap((reference) => {
      const claim = claimById.get(reference.claim_id);
      assert(
        claim,
        `Cannot resolve claim kind for ${reference.claim_id}`
      );
      if (claim.kind !== "table") return [];
      assert(
        reference.table_cell_ids?.length > 0,
        `Table claim ${reference.claim_id} has no selected cells`
      );
      return reference.table_cell_ids.map((cellId) => ({
        kind: "claim-cell",
        id: claimCellSubjectId(reference.claim_id, cellId)
      }));
    });
  }
  return answer.claim_refs
    .filter((reference) => {
      const claim = claimById.get(reference.claim_id);
      assert(
        claim,
        `Cannot resolve claim kind for ${reference.claim_id}`
      );
      return !claimKind || claim.kind === claimKind;
    })
    .map((reference) => ({ kind: "claim", id: reference.claim_id }));
}

function validateAnswerSemantics(answer, candidateProfile = validProfile) {
  assert(
    answer.corpus.release_id === corpus.release_id,
    "Unknown corpus release"
  );
  assert(
    answer.corpus.manifest_sha256 === corpus.integrity.artifact_sha256,
    "Corpus manifest digest mismatch"
  );
  assert(
    answer.runtime.manifest_id === runtime.manifest_id,
    "Unknown runtime assurance manifest"
  );
  assert(
    answer.runtime.manifest_sha256 === runtime.integrity.artifact_sha256,
    "Runtime assurance manifest digest mismatch"
  );
  assert(
    runtime.compatible_corpus.release_id === corpus.release_id &&
      runtime.compatible_corpus.manifest_sha256 ===
        corpus.integrity.artifact_sha256,
    "Runtime and corpus manifests are incompatible"
  );
  assert(
    answer.query.canonicalization_id ===
      runtime.query_canonicalization.artifact_id,
    "Query canonicalization is not pinned by the runtime manifest"
  );
  assert(
    answer.renderer.template_set_version ===
      runtime.renderer_templates.artifact_id,
    "Renderer template set is not pinned by the runtime manifest"
  );

  const pageById = new Map(corpus.pages.map((page) => [page.page_id, page]));
  const claimById = new Map(
    candidateProfile.claims.map((claim) => [claim.claim_id, claim])
  );
  const validSubjectKeys = new Set([
    `envelope:${answer.answer_id}`,
    ...answer.claim_refs.map((reference) => `page:${reference.page_id}`),
    ...answer.quote_refs.map((reference) => `page:${reference.page_id}`),
    ...answer.claim_refs.map((reference) => `claim:${reference.claim_id}`),
    ...answer.claim_refs.flatMap((reference) =>
      (reference.table_cell_ids ?? []).map(
        (cellId) =>
          `claim-cell:${claimCellSubjectId(reference.claim_id, cellId)}`
      )
    ),
    ...answer.quote_refs.map((reference) => `quote:${reference.quote_id}`)
  ]);

  for (const reference of answer.claim_refs) {
    const page = pageById.get(reference.page_id);
    assert(page, `Unknown claim page ${reference.page_id}`);
    assert(
      page.review_payload_sha256 === reference.review_payload_sha256,
      `Review-payload digest mismatch for ${reference.page_id}`
    );
    assert(
      page.claim_ids.includes(reference.claim_id),
      `Unknown claim ${reference.claim_id}`
    );
    const claim = claimById.get(reference.claim_id);
    assert(
      claim,
      `Cannot resolve claim kind for ${reference.claim_id}`
    );
    if (claim.kind === "table") {
      assert(
        reference.table_cell_ids?.length > 0,
        `Table claim ${reference.claim_id} has no selected cells`
      );
      const cellIds = new Set(
        claim.table_value.cells.map((cell) => cell.cell_id)
      );
      for (const cellId of reference.table_cell_ids) {
        assert(
          cellIds.has(cellId),
          `Table claim ${reference.claim_id} selects unknown cell ${cellId}`
        );
      }
    } else {
      assert(
        reference.table_cell_ids === undefined,
        `Non-table claim ${reference.claim_id} selects table cells`
      );
    }
  }
  const quoteById = new Map(
    candidateProfile.quotes.map((quote) => [quote.quote_id, quote])
  );
  for (const reference of answer.quote_refs) {
    const page = pageById.get(reference.page_id);
    assert(page, `Unknown quote page ${reference.page_id}`);
    assert(
      page.quote_ids.includes(reference.quote_id),
      `Unknown quote ${reference.quote_id}`
    );
    assert(
      quoteById.get(reference.quote_id)?.span_sha256 === reference.span_sha256,
      `Quote digest mismatch for ${reference.quote_id}`
    );
  }

  for (const check of answer.checks) {
    for (const subject of check.subjects) {
      assert(
        validSubjectKeys.has(subjectKey(subject)),
        `Check ${check.check_id} covers unknown subject ${subjectKey(subject)}`
      );
    }
  }

  for (const rule of runtime.required_checks.filter(
    (candidate) => candidate.outcome === answer.outcome
  )) {
    const subjects = expectedSubjects(
      answer,
      rule.subject_kind,
      rule.claim_kind,
      candidateProfile
    );
    for (const subject of subjects) {
      for (const checkId of rule.check_ids) {
        assert(
          checkCovers(
            answer,
            checkId,
            subject,
            answer.outcome === "evidence-backed"
          ),
          `Missing required ${checkId} check for ${subjectKey(subject)}`
        );
      }
    }
  }

  for (const reason of answer.outcome_reasons) {
    const rule = runtime.outcome_reason_rules.find(
      (candidate) =>
        candidate.code === reason.code &&
        candidate.source_kind === reason.source_kind
    );
    assert(rule, `No runtime reason rule for ${reason.code}`);
    assert(
      rule.source_ids.includes(reason.source_id),
      `Reason ${reason.code} cannot originate from ${reason.source_id}`
    );
    if (reason.source_kind === "check") {
      const matching = answer.checks.find(
        (check) =>
          check.check_id === reason.source_id &&
          check.verdict !== "pass" &&
          reason.subjects.every((subject) =>
            check.subjects.some(
              (candidate) => subjectKey(candidate) === subjectKey(subject)
            )
          )
      );
      assert(matching, `Reason ${reason.code} lacks a matching failed check`);
    }
  }
}

for (const answer of [evidenceBacked, evidenceOnly, abstention]) {
  validateAnswerSemantics(answer);
}

function validateAuditSemantics(candidateAudit) {
  assert(
    candidateAudit.corpus.release_id === corpus.release_id &&
      candidateAudit.corpus.manifest_sha256 ===
        corpus.integrity.artifact_sha256,
    "Audit corpus manifest mismatch"
  );
  assert(
    candidateAudit.runtime.manifest_id === runtime.manifest_id &&
      candidateAudit.runtime.manifest_sha256 ===
        runtime.integrity.artifact_sha256,
    "Audit runtime manifest mismatch"
  );
  assert(
    candidateAudit.query.canonicalization_id ===
      runtime.query_canonicalization.artifact_id,
    "Audit query canonicalization mismatch"
  );
  uniqueBy(candidateAudit.retrieval.candidates, "page_id", "Audit candidates");
  const candidateById = new Map(
    candidateAudit.retrieval.candidates.map((candidate) => [
      candidate.page_id,
      candidate
    ])
  );
  for (const pageId of candidateAudit.retrieval.selected_page_ids) {
    assert(candidateById.get(pageId)?.eligible, `Selected page ${pageId} is ineligible`);
  }
  uniqueBy(candidateAudit.generation.attempts, "attempt", "Generation attempts");
  const accepted = candidateAudit.generation.attempts.filter(
    (attempt) => attempt.attempt === candidateAudit.generation.accepted_attempt
  );
  assert(accepted.length === 1, "accepted_attempt does not resolve uniquely");
  assert(
    accepted[0].rejection_codes.length === 0,
    "Accepted generation attempt carries rejection codes"
  );
  const selectedPages = corpus.pages.filter((page) =>
    candidateAudit.retrieval.selected_page_ids.includes(page.page_id)
  );
  const selectedClaimIds = new Set(selectedPages.flatMap((page) => page.claim_ids));
  const selectedQuoteIds = new Set(selectedPages.flatMap((page) => page.quote_ids));
  for (const claimId of accepted[0].candidate_claim_ids) {
    assert(selectedClaimIds.has(claimId), `Accepted unknown claim ${claimId}`);
  }
  for (const quoteId of accepted[0].candidate_quote_ids) {
    assert(selectedQuoteIds.has(quoteId), `Accepted unknown quote ${quoteId}`);
  }
}

validateAuditSemantics(audit);

function applyOperations(base, operations) {
  const copy = structuredClone(base);
  function resolve(pointer) {
    const segments = pointer
      .split("/")
      .slice(1)
      .map((segment) => segment.replaceAll("~1", "/").replaceAll("~0", "~"));
    let value = copy;
    for (const segment of segments) {
      value = value[Array.isArray(value) ? Number(segment) : segment];
    }
    return value;
  }
  for (const operation of operations) {
    const segments = operation.path
      .split("/")
      .slice(1)
      .map((segment) => segment.replaceAll("~1", "/").replaceAll("~0", "~"));
    const finalSegment = segments.pop();
    let target = copy;
    for (const segment of segments) {
      target = target[Array.isArray(target) ? Number(segment) : segment];
    }
    if (operation.operation === "remove") {
      if (Array.isArray(target)) target.splice(Number(finalSegment), 1);
      else delete target[finalSegment];
    } else if (operation.operation === "copy") {
      const value = structuredClone(resolve(operation.from));
      if (Array.isArray(target) && finalSegment === "-") target.push(value);
      else target[Array.isArray(target) ? Number(finalSegment) : finalSegment] = value;
    } else if (Array.isArray(target) && finalSegment === "-") {
      target.push(operation.value);
    } else {
      target[Array.isArray(target) ? Number(finalSegment) : finalSegment] =
        operation.value;
    }
  }
  return copy;
}

const mutationValidators = {
  "answer-schema": (value) =>
    validateWith(schemaIds.answer, value, "Mutated answer"),
  "answer-semantic": (value) => {
    validateWith(schemaIds.answer, value, "Mutated answer");
    validateAnswerSemantics(value);
  },
  "profile-schema": (value) =>
    validateWith(schemaIds.profile, value, "Mutated profile"),
  "profile-semantic": (value) => {
    validateWith(schemaIds.profile, value, "Mutated profile");
    validateProfileSemantics(value, sourceRegistry);
  },
  "answer-profile-resolution-semantic": (value) => {
    validateWith(schemaIds.profile, value, "Mutated profile");
    validateProfileSemantics(value, sourceRegistry);
    validateAnswerSemantics(evidenceBacked, value);
  },
  "source-registry-semantic": (value) => {
    validateWith(schemaIds.source, value, "Mutated source registry");
    validateSourceRegistrySemantics(value);
  },
  "reviewer-event-semantic": (value) => {
    validateWith(schemaIds.reviewer, value, "Mutated reviewer registry");
    reviewerForEvent(
      "human.skitch",
      "editorial-accuracy",
      "2026-07-28T00:00:00Z",
      value
    );
  },
  "runtime-semantic": (value) => {
    validateWith(schemaIds.runtime, value, "Mutated runtime manifest");
    validateRuntimeManifestSemantics(value);
  },
  "audit-schema": (value) =>
    validateWith(schemaIds.audit, value, "Mutated audit")
};

for (const mutation of mutations.mutations) {
  const value = applyOperations(load(mutation.base), mutation.operations);
  const validator = mutationValidators[mutation.validator];
  assert(validator, `Unknown mutation validator ${mutation.validator}`);
  expectFailure(
    () => validator(value),
    `${mutation.id} mutation did not fail ${mutation.validator}`
  );
}

console.log(
  `Artifact checks passed: ${schemaPaths.length} schemas, ${manifest.cases.length} acceptance cases, full format assertion, and all executable semantic mutations.`
);
