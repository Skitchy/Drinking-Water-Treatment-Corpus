import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");

function load(relativePath) {
  return JSON.parse(fs.readFileSync(path.join(root, relativePath), "utf8"));
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

const schemaPaths = [
  "schemas/drinking-water-profile-v0.1.schema.json",
  "schemas/reviewer-registry-v0.1.schema.json",
  "schemas/verified-answer-v0.1.schema.json",
  "schemas/audit-envelope-v0.1.schema.json"
];

for (const schemaPath of schemaPaths) {
  const schema = load(schemaPath);
  assert(
    schema.$schema === "https://json-schema.org/draft/2020-12/schema",
    `${schemaPath} must declare JSON Schema 2020-12`
  );
  assert(schema.$id, `${schemaPath} must declare a stable $id`);
}

const manifest = load("tests/acceptance/manifest-v0.1.json");
const expectedCaseIds = Array.from(
  { length: 15 },
  (_, index) => `AT-${String(index + 1).padStart(3, "0")}`
);
assert(
  JSON.stringify(manifest.cases.map((testCase) => testCase.id)) ===
    JSON.stringify(expectedCaseIds),
  "Acceptance manifest must contain AT-001 through AT-015 in order"
);

const registry = load(
  "tests/acceptance/fixtures/reviewer-registry-valid.json"
);
const validProfile = load("tests/acceptance/fixtures/profile-valid.json");
const invalidProfile = load(
  "tests/acceptance/fixtures/profile-invalid-review-hash.json"
);
const corpus = load("tests/acceptance/fixtures/corpus-index-v0.1.json");
const evidenceBacked = load(
  "tests/acceptance/fixtures/answer-valid-evidence-backed.json"
);
const evidenceOnly = load(
  "tests/acceptance/fixtures/answer-valid-evidence-only.json"
);
const abstention = load(
  "tests/acceptance/fixtures/answer-valid-abstention.json"
);
const mutations = load(
  "tests/acceptance/fixtures/answer-mutations-v0.1.json"
);

function validateProfileSemantics(profile) {
  const payloadDigest = profile.review_payload.sha256;
  assert(profile.verified.length > 0, "Profile has no verification events");
  for (const event of profile.verified) {
    assert(
      event.review_payload_sha256 === payloadDigest,
      `Verification by ${event.by} is bound to a different review payload`
    );
    if (event.actor_type === "human") {
      const reviewer = registry.reviewers.find(
        (entry) => entry.reviewer_id === event.by
      );
      assert(reviewer, `Unknown reviewer ${event.by}`);
      assert(reviewer.status === "active", `Reviewer ${event.by} is inactive`);
      for (const scope of event.scopes.filter(
        (item) => item !== "source-capture" && item !== "quote-fidelity"
      )) {
        assert(
          reviewer.review_scopes.includes(scope),
          `Reviewer ${event.by} lacks scope ${scope}`
        );
      }
    }
  }
}

validateProfileSemantics(validProfile);
expectFailure(
  () => validateProfileSemantics(invalidProfile),
  "AT-001 fixture must fail review-payload binding"
);

const allowedAnswerKeys = new Set([
  "schema_version",
  "answer_id",
  "created_at",
  "outcome",
  "query_sha256",
  "corpus",
  "policy_version",
  "verifier_version",
  "applicability",
  "claim_refs",
  "quote_refs",
  "checks",
  "reason_codes",
  "renderer",
  "integrity"
]);

function validateAnswerShape(answer) {
  for (const key of Object.keys(answer)) {
    assert(allowedAnswerKeys.has(key), `Unknown answer field: ${key}`);
  }
  for (const key of allowedAnswerKeys) {
    assert(Object.hasOwn(answer, key), `Missing answer field: ${key}`);
  }
  assert(
    ["evidence-backed", "evidence-only", "abstention"].includes(answer.outcome),
    `Unknown answer outcome: ${answer.outcome}`
  );
  if (answer.outcome === "evidence-backed") {
    assert(
      answer.claim_refs.length + answer.quote_refs.length > 0,
      "Evidence-backed answer has no evidence references"
    );
    assert(
      answer.reason_codes.length === 0,
      "Evidence-backed answer has reason codes"
    );
    assert(
      answer.checks.length > 0 &&
        answer.checks.every((check) => check.verdict === "pass"),
      "Evidence-backed answer contains a non-passing check"
    );
  }
  if (answer.outcome === "evidence-only") {
    assert(
      answer.claim_refs.length + answer.quote_refs.length > 0,
      "Evidence-only answer has no evidence references"
    );
    assert(
      answer.reason_codes.length > 0,
      "Evidence-only answer lacks a reason"
    );
  }
  if (answer.outcome === "abstention") {
    assert(
      answer.claim_refs.length === 0,
      "Abstention contains claim references"
    );
    assert(
      answer.quote_refs.length === 0,
      "Abstention contains quote references"
    );
    assert(answer.reason_codes.length > 0, "Abstention lacks a reason");
  }
  if (answer.integrity.mode === "signed") {
    assert(answer.integrity.signature, "Signed answer lacks a signature");
  }
}

function validateAnswerSemantics(answer) {
  assert(
    answer.corpus.release_id === corpus.release_id,
    "Unknown corpus release"
  );
  assert(
    answer.corpus.manifest_sha256 === corpus.manifest_sha256,
    "Corpus manifest digest mismatch"
  );
  const pageById = new Map(corpus.pages.map((page) => [page.page_id, page]));
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
  }
  for (const reference of answer.quote_refs) {
    const page = pageById.get(reference.page_id);
    assert(page, `Unknown quote page ${reference.page_id}`);
    const quote = page.quotes.find(
      (entry) => entry.quote_id === reference.quote_id
    );
    assert(quote, `Unknown quote ${reference.quote_id}`);
    assert(
      quote.span_sha256 === reference.span_sha256,
      `Quote digest mismatch for ${reference.quote_id}`
    );
  }
}

for (const answer of [evidenceBacked, evidenceOnly, abstention]) {
  validateAnswerShape(answer);
  validateAnswerSemantics(answer);
}

function applyMutation(base, mutation) {
  const copy = structuredClone(base);
  const segments = mutation.path
    .split("/")
    .slice(1)
    .map((segment) => segment.replaceAll("~1", "/").replaceAll("~0", "~"));
  const finalSegment = segments.pop();
  let target = copy;
  for (const segment of segments) {
    target = target[Array.isArray(target) ? Number(segment) : segment];
  }
  target[Array.isArray(target) ? Number(finalSegment) : finalSegment] =
    mutation.value;
  return copy;
}

const mutationById = new Map(
  mutations.mutations.map((mutation) => [mutation.id, mutation])
);

const freeTextAnswer = applyMutation(
  evidenceBacked,
  mutationById.get("AT-011")
);
expectFailure(
  () => validateAnswerShape(freeTextAnswer),
  "AT-011 mutation must fail the closed answer surface"
);

const unknownClaimAnswer = applyMutation(
  evidenceBacked,
  mutationById.get("AT-012")
);
validateAnswerShape(unknownClaimAnswer);
expectFailure(
  () => validateAnswerSemantics(unknownClaimAnswer),
  "AT-012 mutation must fail claim resolution"
);

const wrongReleaseAnswer = applyMutation(
  evidenceBacked,
  mutationById.get("AT-013")
);
validateAnswerShape(wrongReleaseAnswer);
expectFailure(
  () => validateAnswerSemantics(wrongReleaseAnswer),
  "AT-013 mutation must fail release-digest resolution"
);

console.log(
  "Artifact checks passed: 4 schemas, 8 fixtures, 15 acceptance cases, and all executable foundation checks."
);
