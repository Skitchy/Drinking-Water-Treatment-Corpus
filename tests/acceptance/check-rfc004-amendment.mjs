import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");
const evaluationTime = new Date("2026-08-01T00:00:00Z");

function load(relativePath) {
  return JSON.parse(fs.readFileSync(path.join(root, relativePath), "utf8"));
}

function sha256File(relativePath) {
  return createHash("sha256")
    .update(fs.readFileSync(path.join(root, relativePath)))
    .digest("hex");
}

function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, stable(value[key])])
    );
  }
  return value;
}

function canonicalDigest(value) {
  const copy = structuredClone(value);
  delete copy.integrity.artifact_sha256;
  return createHash("sha256")
    .update(JSON.stringify(stable(copy)), "utf8")
    .digest("hex");
}

function digestValue(value) {
  return createHash("sha256")
    .update(JSON.stringify(stable(value)), "utf8")
    .digest("hex");
}

function caseReviewPayloadDigest(testCase) {
  const payload = structuredClone(testCase);
  delete payload.compatibility_dispositions;
  return digestValue(payload);
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function expectFailure(fn, message, expectedError) {
  let failure = null;
  try {
    fn();
  } catch (error) {
    failure = error;
  }
  assert(failure, message);
  if (expectedError) {
    assert(
      failure instanceof Error && failure.message.includes(expectedError),
      `${message}; failed for an unrelated reason: ${failure?.message}`
    );
  }
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

const schemaPaths = [
  "schemas/procedure-contract-v0.1.schema.json",
  "schemas/evaluation-manifest-v0.1.schema.json",
  "schemas/runtime-assurance-manifest-v0.2.schema.json",
  "schemas/audit-envelope-v0.2.schema.json",
  "schemas/reviewer-registry-v0.2.schema.json"
];

const ajv = new Ajv2020({ allErrors: true, strict: true });
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

const schemaIds = {
  procedure: "urn:dwtc:schema:procedure-contract:v0.1",
  evaluation: "urn:dwtc:schema:evaluation-manifest:v0.1",
  runtime: "urn:dwtc:schema:runtime-assurance-manifest:v0.2",
  audit: "urn:dwtc:schema:audit-envelope:v0.2",
  reviewer: "urn:dwtc:schema:reviewer-registry:v0.2"
};

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

const procedure = load(
  "tests/acceptance/fixtures/procedure-contract-valid.json"
);
const runtime = load(
  "tests/acceptance/fixtures/runtime-assurance-manifest-v0.2-valid.json"
);
const audit = load(
  "tests/acceptance/fixtures/audit-envelope-v0.2-valid.json"
);
const reviewerRegistry = load(
  "tests/acceptance/fixtures/reviewer-registry-v0.2-valid.json"
);
const evaluation = load(
  "tests/acceptance/fixtures/evaluation-manifest-valid.json"
);
const corpus = load(
  "tests/acceptance/fixtures/corpus-release-manifest-valid.json"
);
const answerTemplate = load(
  "tests/acceptance/fixtures/answer-valid-evidence-backed.json"
);
const mutationSet = load(
  "tests/acceptance/fixtures/artifact-mutations-rfc004-v0.1.json"
);
const amendmentManifest = load(
  "tests/acceptance/manifest-rfc004-amendment-v0.1.json"
);
const canonicalizationVectors = load(
  "tests/acceptance/fixtures/rfc004-canonicalization-vectors-v0.1.json"
);

const boundAnswer = structuredClone(answerTemplate);
boundAnswer.answer_id = "answer.fixture-backed-002";
boundAnswer.runtime = {
  manifest_id: runtime.manifest_id,
  manifest_sha256: runtime.integrity.artifact_sha256
};
boundAnswer.integrity.artifact_sha256 =
  "2222222222222222222222222222222222222222222222222222222222222222";

validateWith(schemaIds.procedure, procedure, "Procedure fixture");
validateWith(schemaIds.runtime, runtime, "Runtime v0.2 fixture");
validateWith(schemaIds.audit, audit, "Audit v0.2 fixture");
validateWith(schemaIds.reviewer, reviewerRegistry, "Reviewer v0.2 fixture");
validateWith(schemaIds.evaluation, evaluation, "Evaluation fixture");

function validateProcedureSemantics(candidate) {
  uniqueBy(candidate.states, "state_id", "Procedure states");
  uniqueBy(candidate.conditions, "condition_id", "Procedure conditions");
  uniqueBy(candidate.controls, "control_id", "Procedure controls");
  uniqueBy(candidate.triggers, "trigger_id", "Procedure triggers");
  uniqueBy(candidate.transitions, "transition_id", "Procedure transitions");
  uniqueBy(candidate.transitions, "order", "Procedure transition order");
  uniqueBy(candidate.terminal_mappings, "state_id", "Terminal mappings");

  const stateById = new Map(candidate.states.map((state) => [state.state_id, state]));
  const conditionById = new Map(
    candidate.conditions.map((condition) => [condition.condition_id, condition])
  );
  const controlById = new Map(
    candidate.controls.map((control) => [control.control_id, control])
  );
  const triggerIds = new Set(candidate.triggers.map((trigger) => trigger.trigger_id));
  const initialStates = candidate.states.filter((state) => state.role === "initial");
  assert(initialStates.length === 1, "Procedure must have exactly one initial state");
  assert(
    initialStates[0].state_id === candidate.initial_state_id,
    "initial_state_id does not identify the initial state"
  );
  for (const trigger of candidate.triggers) {
    const condition = conditionById.get(trigger.condition_id);
    assert(condition, `Trigger ${trigger.trigger_id} has an unknown condition`);
    assert(
      condition.kind === trigger.kind,
      `Trigger ${trigger.trigger_id} and condition ${trigger.condition_id} have different kinds`
    );
  }

  let previousOrder = 0;
  const routeKeys = new Set();
  for (const transition of candidate.transitions) {
    assert(
      transition.order > previousOrder,
      "Procedure transitions are not in strict declared order"
    );
    previousOrder = transition.order;
    assert(stateById.has(transition.from_state_id), "Transition has unknown from-state");
    assert(stateById.has(transition.to_state_id), "Transition has unknown to-state");
    assert(triggerIds.has(transition.trigger_id), "Transition has unknown trigger");
    assert(
      stateById.get(transition.from_state_id).role !== "terminal",
      "Terminal state has an outgoing transition"
    );
    const routeKey = `${transition.from_state_id}:${transition.trigger_id}`;
    assert(!routeKeys.has(routeKey), "Procedure has nondeterministic duplicate route");
    routeKeys.add(routeKey);
  }
  assert(
    candidate.transitions.some((transition) => transition.requirement === "mandatory"),
    "Procedure has no mandatory transition"
  );

  const graph = new Map(candidate.states.map((state) => [state.state_id, []]));
  for (const transition of candidate.transitions) {
    graph.get(transition.from_state_id).push(transition.to_state_id);
  }
  const visited = new Set();
  const visiting = new Set();
  function visit(stateId) {
    assert(!visiting.has(stateId), `Procedure cycle includes ${stateId}`);
    if (visited.has(stateId)) return;
    visiting.add(stateId);
    for (const next of graph.get(stateId)) visit(next);
    visiting.delete(stateId);
    visited.add(stateId);
  }
  visit(candidate.initial_state_id);
  assert(visited.size === candidate.states.length, "Procedure contains unreachable state");

  const terminalIds = candidate.states
    .filter((state) => state.role === "terminal")
    .map((state) => state.state_id);
  assert(
    candidate.terminal_mappings.length === terminalIds.length,
    "Every terminal state must have exactly one mapping"
  );
  for (const mapping of candidate.terminal_mappings) {
    assert(
      terminalIds.includes(mapping.state_id),
      "Terminal mapping identifies a nonterminal state"
    );
    if (mapping.reason_gate) {
      for (const sourceId of mapping.reason_gate.source_ids) {
        const control = controlById.get(sourceId);
        assert(control, `Terminal reason gate has unknown control ${sourceId}`);
        const compatible =
          mapping.reason_gate.source_kind === "check"
            ? control.kind === "check"
            : control.kind.endsWith("-gate");
        assert(
          compatible,
          `Terminal reason source ${sourceId} has incompatible control kind`
        );
      }
    }
  }
  assert(
    candidate.integrity.artifact_sha256 === canonicalDigest(candidate),
    "Procedure integrity digest mismatch"
  );
}

function reviewerForEvent(registry, reviewerId, scope, at) {
  const reviewer = registry.reviewers.find(
    (entry) => entry.reviewer_id === reviewerId
  );
  assert(reviewer, `Unknown reviewer ${reviewerId}`);
  assert(
    reviewer.review_scopes.includes(scope),
    `Reviewer ${reviewerId} lacks scope ${scope}`
  );
  const eventTime = parseTime(at, `Review event ${reviewerId}`);
  const statusChangedAt = parseTime(
    reviewer.status_changed_at,
    `status_changed_at ${reviewerId}`
  );
  if (reviewer.status !== "active") {
    assert(
      eventTime < statusChangedAt,
      `Reviewer ${reviewerId} was not active at the review event`
    );
  }
  if (
    reviewer.status === "revoked" &&
    reviewer.revocation?.invalidates_prior_reviews
  ) {
    const effectiveAt = parseTime(
      reviewer.revocation.effective_at,
      `revocation ${reviewerId}`
    );
    assert(
      eventTime < effectiveAt,
      `Reviewer ${reviewerId} event is invalidated by revocation`
    );
  }
  const from = parseTime(reviewer.authorized_from, "authorized_from");
  const through = reviewer.authorized_through
    ? parseTime(reviewer.authorized_through, "authorized_through")
    : null;
  assert(
    eventTime >= from && (!through || eventTime <= through),
    `Reviewer ${reviewerId} is outside the authorization interval`
  );
  const qualificationCoversEvent = reviewer.qualifications.some((qualification) => {
    const validFrom = parseTime(`${qualification.valid_from}T00:00:00Z`, "valid_from");
    const expiresAt = qualification.expires_at
      ? parseTime(`${qualification.expires_at}T23:59:59Z`, "expires_at")
      : null;
    return eventTime >= validFrom && (!expiresAt || eventTime <= expiresAt);
  });
  assert(
    qualificationCoversEvent,
    `Reviewer ${reviewerId} lacks a qualification covering the event`
  );
}

function validateRuntimeSemantics(candidate) {
  assert(
    candidate.compatible_corpus.release_id === corpus.release_id &&
      candidate.compatible_corpus.manifest_sha256 ===
        corpus.integrity.artifact_sha256,
    "Runtime and corpus are incompatible"
  );
  assert(
    candidate.required_check_baseline.sha256 ===
      sha256File("contracts/assurance-check-baseline-v0.1.json"),
    "Runtime required-check baseline digest mismatch"
  );
  assert(
    candidate.audit_schema.artifact_id ===
      "urn:dwtc:schema:audit-envelope:v0.2",
    "Runtime v0.2 does not pin audit-envelope/v0.2"
  );
  assert(
    candidate.procedure_contract.artifact_id === procedure.contract_id,
    "Runtime names the wrong procedure contract"
  );
  assert(
    candidate.procedure_contract.sha256 === procedure.integrity.artifact_sha256,
    "Runtime procedure-contract digest mismatch"
  );
  assert(
    candidate.runbook.compatible_procedure_contract_sha256 ===
      candidate.procedure_contract.sha256,
    "Runbook is compatible with a different procedure contract"
  );
  assert(
    new Set(candidate.runbook.fallback_reason_ids).size ===
      candidate.runbook.fallback_reason_ids.length,
    "Runbook has duplicate fallback-reason IDs"
  );
  assert(
    new Set(candidate.runbook.gotcha_check_ids).size ===
      candidate.runbook.gotcha_check_ids.length,
    "Runbook has duplicate gotcha-check IDs"
  );
  const reviewedAt = parseTime(candidate.runbook.reviewed_at, "runbook.reviewed_at");
  const nextDueAt = parseTime(candidate.runbook.next_due_at, "runbook.next_due_at");
  assert(reviewedAt < nextDueAt, "Runbook review does not precede next_due_at");
  assert(
    evaluationTime < nextDueAt,
    "Runbook is overdue at runtime qualification time"
  );
  assert(
    candidate.integrity.artifact_sha256 === canonicalDigest(candidate),
    "Runtime v0.2 integrity digest mismatch"
  );
}

function selectionCount(selection) {
  return selection.claim_ids.length + selection.quote_ids.length + selection.cell_ids.length;
}

function assertDisjointEvidenceSelection(selection, forbidden, label) {
  for (const idKind of ["claim_ids", "quote_ids", "cell_ids"]) {
    const forbiddenIds = new Set(forbidden[idKind]);
    for (const id of selection[idKind]) {
      assert(!forbiddenIds.has(id), `${label} also forbids ${id}`);
    }
  }
}

function validateEvaluationSemantics(candidate, candidateRegistry = reviewerRegistry) {
  const compatibility = candidate.compatibility;
  assert(
    compatibility.corpus_release.release_id === corpus.release_id &&
      compatibility.corpus_release.manifest_sha256 ===
        corpus.integrity.artifact_sha256,
    "Evaluation corpus compatibility mismatch"
  );
  assert(
    compatibility.procedure_contract.artifact_id === procedure.contract_id &&
      compatibility.procedure_contract.sha256 ===
        procedure.integrity.artifact_sha256,
    "Evaluation procedure compatibility mismatch"
  );
  assert(
    compatibility.runbook.artifact_id === runtime.runbook.artifact_id &&
      compatibility.runbook.sha256 === runtime.runbook.sha256,
    "Evaluation runbook compatibility mismatch"
  );
  assert(
    compatibility.runtime.manifest_id === runtime.manifest_id &&
      compatibility.runtime.manifest_sha256 ===
        runtime.integrity.artifact_sha256,
    "Evaluation runtime compatibility mismatch"
  );
  assert(
    compatibility.evaluation_schema.sha256 ===
      sha256File("schemas/evaluation-manifest-v0.1.schema.json"),
    "Evaluation-schema digest mismatch"
  );
  assert(
    compatibility.grader.sha256 ===
      sha256File("tests/acceptance/check-rfc004-amendment.mjs"),
    "Evaluation grader digest mismatch"
  );

  const activeCases = [
    ...candidate.conformance_suite.cases,
    ...candidate.capability_challenge_set.cases
  ];
  const retiredCases = candidate.capability_challenge_set.retired_cases;
  const allCases = [...activeCases, ...retiredCases];
  uniqueBy(allCases, "case_id", "Evaluation cases");
  const poolPolicy = candidate.capability_challenge_set.rotation_policy;
  const activeCapabilityCount = candidate.capability_challenge_set.cases.length;
  assert(
    poolPolicy.minimum_active_cases <= poolPolicy.maximum_active_cases,
    "Capability pool minimum exceeds its maximum"
  );
  assert(
    activeCapabilityCount >= poolPolicy.minimum_active_cases &&
      activeCapabilityCount <= poolPolicy.maximum_active_cases,
    "Capability challenge set is outside its declared active-case bounds"
  );
  const allDispositions = allCases.flatMap(
    (testCase) => testCase.compatibility_dispositions
  );
  uniqueBy(allDispositions, "disposition_id", "Evaluation dispositions");

  for (const testCase of allCases) {
    assert(
      testCase.corpus_manifest_sha256 ===
        compatibility.corpus_release.manifest_sha256,
      `Case ${testCase.case_id} pins the wrong corpus`
    );
    if (testCase.oracle.kind === "evidence-backed") {
      assert(
        selectionCount(testCase.oracle.required_selection) > 0,
        `Case ${testCase.case_id} has an empty required evidence selection`
      );
      assertDisjointEvidenceSelection(
        testCase.oracle.required_selection,
        testCase.oracle.forbidden_selection,
        `Case ${testCase.case_id} required selection`
      );
      for (const alternative of testCase.oracle.allowed_alternatives) {
        assert(
          selectionCount(alternative) > 0,
          `Case ${testCase.case_id} has an empty allowed alternative`
        );
        assertDisjointEvidenceSelection(
          alternative,
          testCase.oracle.forbidden_selection,
          `Case ${testCase.case_id} allowed alternative`
        );
      }
    }
    let previousReviewTime = null;
    for (const disposition of testCase.compatibility_dispositions) {
      const reviewTime = parseTime(disposition.reviewed_at, "disposition.reviewed_at");
      assert(
        !previousReviewTime || reviewTime >= previousReviewTime,
        `Case ${testCase.case_id} dispositions are not chronological`
      );
      previousReviewTime = reviewTime;
      reviewerForEvent(
        candidateRegistry,
        disposition.reviewed_by,
        "procedure-domain",
        disposition.reviewed_at
      );
      assert(
        disposition.case_review_payload_sha256 ===
          caseReviewPayloadDigest(testCase),
        `Case ${testCase.case_id} disposition is bound to different case content`
      );
      assert(
        disposition.corpus_manifest_sha256 ===
          compatibility.corpus_release.manifest_sha256 &&
          disposition.procedure_contract_sha256 ===
            compatibility.procedure_contract.sha256 &&
          disposition.runbook_sha256 === compatibility.runbook.sha256 &&
          disposition.runtime_manifest_sha256 ===
            compatibility.runtime.manifest_sha256,
        `Case ${testCase.case_id} has a stale compatibility disposition`
      );
    }
  }

  for (const testCase of activeCases) {
    assert(
      testCase.compatibility_dispositions.at(-1).status === "accepted",
      `Active case ${testCase.case_id} is not currently accepted`
    );
  }
  for (const testCase of retiredCases) {
    assert(
      testCase.compatibility_dispositions
        .slice(0, -1)
        .some((disposition) => disposition.status === "accepted"),
      `Retired case ${testCase.case_id} has no prior accepted disposition`
    );
    assert(
      testCase.compatibility_dispositions.at(-1).status === "retired",
      `Retired case ${testCase.case_id} does not end in retirement`
    );
  }
  assert(
    candidate.integrity.artifact_sha256 === canonicalDigest(candidate),
    "Evaluation manifest integrity digest mismatch"
  );
}

function validateAuditSemantics(candidate) {
  assert(
    candidate.corpus.release_id === corpus.release_id &&
      candidate.corpus.manifest_sha256 === corpus.integrity.artifact_sha256,
    "Audit corpus manifest mismatch"
  );
  assert(
    candidate.runtime.manifest_id === runtime.manifest_id &&
      candidate.runtime.manifest_sha256 === runtime.integrity.artifact_sha256,
    "Audit runtime manifest mismatch"
  );
  assert(candidate.procedure, "Procedure-aware runtime requires an audit procedure block");
  assert(
    candidate.procedure.contract.artifact_id === runtime.procedure_contract.artifact_id &&
      candidate.procedure.contract.sha256 === runtime.procedure_contract.sha256,
    "Audit procedure contract does not equal the runtime pin"
  );
  assert(
    candidate.answer.answer_id === boundAnswer.answer_id &&
      candidate.answer.artifact_sha256 === boundAnswer.integrity.artifact_sha256,
    "Audit does not bind the exact verified answer"
  );
  assert(candidate.outcome === boundAnswer.outcome, "Audit and answer outcomes disagree");
  assert(
    candidate.query.canonicalization_id === runtime.query_canonicalization.artifact_id,
    "Audit query canonicalization mismatch"
  );

  uniqueBy(candidate.retrieval.candidates, "page_id", "Audit candidates");
  const candidateById = new Map(
    candidate.retrieval.candidates.map((entry) => [entry.page_id, entry])
  );
  for (const pageId of candidate.retrieval.selected_page_ids) {
    assert(candidateById.get(pageId)?.eligible, `Selected page ${pageId} is ineligible`);
  }
  uniqueBy(candidate.generation.attempts, "attempt", "Generation attempts");
  const accepted = candidate.generation.attempts.filter(
    (attempt) => attempt.attempt === candidate.generation.accepted_attempt
  );
  assert(accepted.length === 1, "accepted_attempt does not resolve uniquely");
  assert(accepted[0].rejection_codes.length === 0, "Accepted attempt has rejection codes");

  const transitionById = new Map(
    procedure.transitions.map((transition) => [transition.transition_id, transition])
  );
  const traversedFallbackTransitions = [];
  let currentState = procedure.initial_state_id;
  let previousContractOrder = 0;
  candidate.procedure.transitions.forEach((observed, index) => {
    assert(observed.ordinal === index + 1, "Observed transition ordinals are not contiguous");
    const declared = transitionById.get(observed.transition_id);
    assert(declared, `Unknown observed transition ${observed.transition_id}`);
    assert(observed.from_state_id === currentState, "Observed transition path is discontinuous");
    assert(
      observed.from_state_id === declared.from_state_id &&
        observed.trigger_id === declared.trigger_id &&
        observed.to_state_id === declared.to_state_id,
      `Observed transition ${observed.transition_id} does not match the contract`
    );
    assert(
      declared.order > previousContractOrder,
      "Observed path violates procedure ordering"
    );
    previousContractOrder = declared.order;
    currentState = observed.to_state_id;
    if (declared.kind === "fallback-entry") {
      traversedFallbackTransitions.push(declared.transition_id);
    }
  });
  assert(
    currentState === candidate.procedure.terminal_state_id,
    "Observed path does not end at terminal_state_id"
  );
  const terminal = procedure.terminal_mappings.find(
    (mapping) => mapping.state_id === candidate.procedure.terminal_state_id
  );
  assert(terminal, "Audit terminates at an unmapped state");
  assert(terminal.outcome === candidate.outcome, "Terminal mapping and audit outcome disagree");

  const fallbackUsed = traversedFallbackTransitions.length > 0;
  assert(
    candidate.procedure.fallback.authorized === fallbackUsed,
    fallbackUsed
      ? "Fallback-marked traversal is not authorized by the audit"
      : "Fallback is authorized without a fallback-marked traversal"
  );
  if (candidate.procedure.fallback.authorized) {
    assert(
      candidate.procedure.structured_claim_resolution.result === "not-covered",
      "Fallback was authorized before structured resolution showed no coverage"
    );
    assert(
      runtime.runbook.fallback_reason_ids.includes(
        candidate.procedure.fallback.reason_id
      ),
      "Fallback reason is not declared by the pinned runbook"
    );
  }
  uniqueBy(candidate.procedure.gates, "gate_id", "Audit procedure gates");
  const controlById = new Map(
    procedure.controls.map((control) => [control.control_id, control])
  );
  for (const gate of candidate.procedure.gates) {
    const control = controlById.get(gate.gate_id);
    assert(control, `Audit procedure gate ${gate.gate_id} is undeclared`);
    assert(
      control.kind === `${gate.kind}-gate`,
      `Audit procedure gate ${gate.gate_id} has incompatible kind`
    );
  }
  if (terminal.reason_gate) {
    for (const sourceId of terminal.reason_gate.source_ids) {
      if (terminal.reason_gate.source_kind === "policy-gate") {
        assert(
          candidate.procedure.gates.some(
            (gate) => gate.gate_id === sourceId && gate.verdict === "reached"
          ),
          `Terminal reason gate ${sourceId} was not reached`
        );
      } else {
        assert(
          candidate.checks.some(
            (check) => check.check_id === sourceId && check.verdict !== "pass"
          ),
          `Terminal reason check ${sourceId} did not record a non-passing verdict`
        );
      }
    }
  }
  uniqueBy(candidate.procedure.gotcha_checks, "check_id", "Audit gotcha checks");
  const observedGotchas = new Set(
    candidate.procedure.gotcha_checks.map((check) => check.check_id)
  );
  assert(
    observedGotchas.size === runtime.runbook.gotcha_check_ids.length &&
      runtime.runbook.gotcha_check_ids.every((checkId) =>
        observedGotchas.has(checkId)
      ),
    "Audit does not account for every gotcha check declared by the runbook"
  );
  assert(
    candidate.integrity.artifact_sha256 === canonicalDigest(candidate),
    "Audit integrity digest mismatch"
  );
}

validateProcedureSemantics(procedure);
validateRuntimeSemantics(runtime);
validateAuditSemantics(audit);
validateEvaluationSemantics(evaluation);

for (const vector of canonicalizationVectors.vectors) {
  const artifact = load(vector.artifact);
  assert(
    artifact.integrity.canonicalization === vector.canonicalization,
    `${vector.artifact} names a different canonicalization`
  );
  assert(
    canonicalDigest(artifact) === vector.expected_sha256 &&
      artifact.integrity.artifact_sha256 === vector.expected_sha256,
    `${vector.artifact} does not match its canonicalization vector`
  );
}

const expectedIds = Array.from(
  { length: 41 },
  (_, index) => `AT-${String(index + 41).padStart(3, "0")}`
);
assert(
  JSON.stringify(amendmentManifest.cases.map((testCase) => testCase.id)) ===
    JSON.stringify(expectedIds),
  "RFC 004 acceptance manifest must contain AT-041 through AT-081 in order"
);
for (const testCase of amendmentManifest.cases) {
  for (const artifact of testCase.artifacts) {
    assert(
      fs.existsSync(path.join(root, artifact)),
      `${testCase.id} references missing artifact ${artifact}`
    );
  }
}
const executableCaseIds = amendmentManifest.cases
  .filter((testCase) => testCase.status === "executable-candidate")
  .map((testCase) => testCase.id);
assert(
  JSON.stringify(mutationSet.mutations.map((mutation) => mutation.id)) ===
    JSON.stringify(executableCaseIds),
  "Every executable RFC 004 case must have exactly one ordered mutation"
);

function applyOperations(base, operations) {
  const copy = structuredClone(base);
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
    } else if (Array.isArray(target) && finalSegment === "-") {
      target.push(structuredClone(operation.value));
    } else {
      target[Array.isArray(target) ? Number(finalSegment) : finalSegment] =
        structuredClone(operation.value);
    }
  }
  return copy;
}

const mutationValidators = {
  "procedure-schema": (value) =>
    validateWith(schemaIds.procedure, value, "Mutated procedure"),
  "procedure-semantic": (value) => {
    validateWith(schemaIds.procedure, value, "Mutated procedure");
    validateProcedureSemantics(value);
  },
  "runtime-schema": (value) =>
    validateWith(schemaIds.runtime, value, "Mutated runtime"),
  "runtime-semantic": (value) => {
    validateWith(schemaIds.runtime, value, "Mutated runtime");
    validateRuntimeSemantics(value);
  },
  "audit-semantic": (value) => {
    validateWith(schemaIds.audit, value, "Mutated audit");
    validateAuditSemantics(value);
  },
  "evaluation-schema": (value) =>
    validateWith(schemaIds.evaluation, value, "Mutated evaluation"),
  "evaluation-semantic": (value) => {
    validateWith(schemaIds.evaluation, value, "Mutated evaluation");
    validateEvaluationSemantics(value);
  },
  "evaluation-reviewer-semantic": (value) => {
    validateWith(schemaIds.reviewer, value, "Mutated reviewer registry");
    validateEvaluationSemantics(evaluation, value);
  }
};

for (const mutation of mutationSet.mutations) {
  const value = applyOperations(load(mutation.base), mutation.operations);
  if (mutation.rebind_case_reviews) {
    const cases = [
      ...value.conformance_suite.cases,
      ...value.capability_challenge_set.cases,
      ...value.capability_challenge_set.retired_cases
    ];
    for (const testCase of cases) {
      const payloadDigest = caseReviewPayloadDigest(testCase);
      for (const disposition of testCase.compatibility_dispositions) {
        disposition.case_review_payload_sha256 = payloadDigest;
      }
    }
  }
  if (mutation.rebind_integrity && value.integrity) {
    value.integrity.artifact_sha256 = canonicalDigest(value);
  }
  const validator = mutationValidators[mutation.validator];
  assert(validator, `Unknown mutation validator ${mutation.validator}`);
  expectFailure(
    () => validator(value),
    `${mutation.id} mutation did not fail ${mutation.validator}`,
    mutation.expected_error
  );
}

console.log(
  `RFC 004 amendment checks passed: ${schemaPaths.length} schemas and ${amendmentManifest.cases.filter((testCase) => testCase.status === "executable-candidate").length} executable cases; ${amendmentManifest.cases.filter((testCase) => testCase.status === "specified").length} integration cases remain explicitly specified.`
);
