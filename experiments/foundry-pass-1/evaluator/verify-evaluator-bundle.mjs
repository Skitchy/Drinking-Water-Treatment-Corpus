import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const evaluatorRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(evaluatorRoot, "../../..");
const relativeEvaluatorRoot = "experiments/foundry-pass-1/evaluator";
const requestedMode = process.argv.find((argument) => argument.startsWith("--mode="))?.split("=")[1] ?? "public";

assert(["public", "maintainer"].includes(requestedMode), "--mode must be public or maintainer");

const absolute = (relativePath) => path.join(repoRoot, relativePath);
const exists = (relativePath) => fs.existsSync(absolute(relativePath));
const bytes = (relativePath) => fs.readFileSync(absolute(relativePath));
const size = (relativePath) => fs.statSync(absolute(relativePath)).size;
const sha256 = (relativePath) =>
  crypto.createHash("sha256").update(bytes(relativePath)).digest("hex");
const readJson = (relativePath) => JSON.parse(bytes(relativePath).toString("utf8"));

function canonicalMemberPairs(members) {
  return JSON.stringify(
    members
      .map(({ path: memberPath, sha256: memberSha256 }) => ({
        path: memberPath,
        sha256: memberSha256,
      }))
      .sort((left, right) => left.path.localeCompare(right.path)),
  );
}

function validateMembers(members, label, requireFiles) {
  const memberPaths = members.map((member) => member.path);
  assert.deepEqual(memberPaths, [...memberPaths].sort(), `${label}: member path order`);

  for (const member of members) {
    if (!requireFiles) {
      assert.equal(exists(member.path), false, `${label}: sealed member leaked into public checkout: ${member.path}`);
      continue;
    }
    assert.equal(size(member.path), member.byte_length, `${label}: byte length for ${member.path}`);
    assert.equal(sha256(member.path), member.sha256, `${label}: sha256 for ${member.path}`);
  }
}

function validateInputManifest(relativePath) {
  const manifest = readJson(relativePath);
  assert.equal(
    manifest.members.length,
    manifest.bundle_identity.member_count,
    `${relativePath}: member count`,
  );
  validateMembers(manifest.members, relativePath, true);

  const logicalDigest = crypto
    .createHash("sha256")
    .update(canonicalMemberPairs(manifest.members))
    .digest("hex");
  assert.equal(
    logicalDigest,
    manifest.bundle_identity.bundle_sha256,
    `${relativePath}: logical bundle digest`,
  );
  return manifest;
}

function validateEvaluatorManifest(relativePath) {
  const manifest = readJson(relativePath);
  const publicMembers = manifest.members;
  const sealedMembers = manifest.sealed_members;

  assert.equal(publicMembers.length, manifest.bundle_identity.public_member_count, "public evaluator member count");
  assert.equal(sealedMembers.length, manifest.bundle_identity.sealed_member_count, "sealed evaluator member count");
  assert.equal(
    publicMembers.length + sealedMembers.length,
    manifest.bundle_identity.member_count,
    "complete evaluator member count",
  );
  assert.equal(
    new Set([...publicMembers, ...sealedMembers].map((member) => member.path)).size,
    publicMembers.length + sealedMembers.length,
    "public and sealed evaluator member paths must be disjoint",
  );

  validateMembers(publicMembers, `${relativePath}: public`, true);
  validateMembers(sealedMembers, `${relativePath}: sealed`, requestedMode === "maintainer");

  const logicalDigest = crypto
    .createHash("sha256")
    .update(canonicalMemberPairs([...publicMembers, ...sealedMembers]))
    .digest("hex");
  assert.equal(logicalDigest, manifest.bundle_identity.bundle_sha256, "complete evaluator bundle digest");
  return manifest;
}

for (const filename of fs.readdirSync(evaluatorRoot).filter((name) => name.endsWith(".json"))) {
  readJson(`${relativeEvaluatorRoot}/${filename}`);
}

const inputManifestPath = `${relativeEvaluatorRoot}/input-manifest.json`;
const evaluatorManifestPath = `${relativeEvaluatorRoot}/evaluator-bundle-manifest.json`;
const inputManifest = validateInputManifest(inputManifestPath);

for (const record of inputManifest.upstream_provenance) {
  assert.equal(size(record.path), record.byte_length, `upstream byte length for ${record.path}`);
  assert.equal(sha256(record.path), record.sha256, `upstream sha256 for ${record.path}`);
}

const captures = inputManifest.members.filter((member) => member.role === "authoritative-capture");
assert.equal(captures.length, 28, "closed input must contain 28 authoritative captures");
assert.equal(
  inputManifest.members.filter((member) => member.role === "source-policy-and-authority-tier-record").length,
  1,
  "closed input must contain one source policy record",
);
assert.equal(
  inputManifest.members.filter((member) => member.role === "target-vocabulary").length,
  1,
  "closed input must contain one target schema",
);
assert.equal(
  inputManifest.members.filter((member) => member.role === "ingestion-job-declaration").length,
  1,
  "closed input must contain one ingestion job",
);
assert.equal(
  inputManifest.members.some(
    (member) =>
      member.path.startsWith("pages/") ||
      member.path === "README.md" ||
      member.path === "sources/source-registry.dbp-first-proof.json",
  ),
  false,
  "closed input leaked evaluator-only or out-of-scope repository material",
);

const sourcePolicy = readJson(`${relativeEvaluatorRoot}/input-source-policy.json`);
assert.equal(
  size(sourcePolicy.upstream_registry.path),
  sourcePolicy.upstream_registry.byte_length,
  "source-policy upstream registry byte length",
);
assert.equal(
  sha256(sourcePolicy.upstream_registry.path),
  sourcePolicy.upstream_registry.sha256,
  "source-policy upstream registry sha256",
);

const sourceRegistry = readJson(sourcePolicy.upstream_registry.path);
const registryBySourceId = new Map(sourceRegistry.sources.map((source) => [source.source_id, source]));
for (const capture of captures) {
  const registrySource = registryBySourceId.get(capture.source_id);
  assert(registrySource, `source registry is missing ${capture.source_id}`);
  assert.equal(registrySource.captured_sha256, capture.sha256, `registry capture digest for ${capture.source_id}`);
  assert.equal(registrySource.authority.class, capture.authority_tier, `authority tier for ${capture.source_id}`);
  assert.equal(
    registrySource.reproduction_decision.status,
    capture.reproduction_decision.status,
    `reproduction status for ${capture.source_id}`,
  );
  assert.equal(
    registrySource.reproduction_decision.classification,
    capture.reproduction_decision.classification,
    `reproduction classification for ${capture.source_id}`,
  );
  assert.equal(
    registrySource.reproduction_decision.decision_payload_sha256,
    capture.reproduction_decision.payload_sha256,
    `reproduction decision digest for ${capture.source_id}`,
  );
}

const census = readJson(`${relativeEvaluatorRoot}/census-oracle.json`);
assert.equal(census.sections.length, census.expected.regulatory_section_count, "census section count");
assert.equal(new Set(census.sections.map((section) => section.citation)).size, 38, "unique census citations");
assert.equal(
  new Set(census.sections.map((section) => section.capture_path)).size,
  census.expected.capture_unit_count,
  "census capture-unit count",
);
assert.deepEqual(
  [...new Set(census.sections.map((section) => section.capture_path))].sort(),
  captures.map((capture) => capture.path).sort(),
  "census and closed-input capture sets",
);
for (const section of census.sections) {
  assert.equal(sha256(section.capture_path), section.capture_sha256, `census capture digest for ${section.citation}`);
}

const calibration = readJson(`${relativeEvaluatorRoot}/calibration-oracle.json`);
let quoteCount = 0;
let claimCount = 0;
for (const oraclePage of calibration.ground_truth_pages) {
  assert.equal(size(oraclePage.path), oraclePage.byte_length, `calibration byte length for ${oraclePage.path}`);
  assert.equal(sha256(oraclePage.path), oraclePage.sha256, `calibration sha256 for ${oraclePage.path}`);
  const page = readJson(oraclePage.path);
  assert.equal(page.page_id, oraclePage.page_id, `calibration page id for ${oraclePage.path}`);
  assert.deepEqual(
    page.quotes.map((quote) => quote.quote_id),
    oraclePage.expected_quote_ids,
    `calibration quote ids for ${oraclePage.path}`,
  );
  assert.deepEqual(
    page.claims.map((claim) => claim.claim_id),
    oraclePage.expected_claim_ids,
    `calibration claim ids for ${oraclePage.path}`,
  );
  quoteCount += page.quotes.length;
  claimCount += page.claims.length;
}
assert.equal(quoteCount, calibration.expected_totals.quotes, "calibration quote count");
assert.equal(claimCount, calibration.expected_totals.claims, "calibration claim count");

const pageRubric = readJson(`${relativeEvaluatorRoot}/page-matching-rubric.json`);
assert.equal(pageRubric.planned_concepts.length, 17, "page-rubric concept count");
assert.equal(size(pageRubric.ground_truth.path), pageRubric.ground_truth.byte_length, "page-plan byte length");
assert.equal(sha256(pageRubric.ground_truth.path), pageRubric.ground_truth.sha256, "page-plan sha256");

const questionRubric = readJson(`${relativeEvaluatorRoot}/challenge-question-rubric.json`);
assert.equal(size(questionRubric.reference_bank.path), questionRubric.reference_bank.byte_length, "question-bank byte length");
assert.equal(sha256(questionRubric.reference_bank.path), questionRubric.reference_bank.sha256, "question-bank sha256");

const probeContract = readJson(`${relativeEvaluatorRoot}/probe-contract.json`);
assert.equal(probeContract.probes.length, probeContract.probe_counts.total, "public probe count");
assert.equal(
  probeContract.probes.filter((probe) => probe.payload_visibility === "sealed").length,
  probeContract.probe_counts.sealed_payloads,
  "sealed probe count",
);
assert.equal(
  probeContract.probes.filter((probe) => probe.payload_visibility === "public").length,
  probeContract.probe_counts.public_payloads,
  "public probe count",
);

if (requestedMode === "maintainer") {
  const probes = readJson(probeContract.sealed_payload.path);
  assert.equal(probes.probes.length, probeContract.probe_counts.total, "sealed probe count");
  assert.equal(
    probes.probes.find((probe) => probe.probe_id === "probe.isolation").attempts.length,
    2,
    "isolation-probe attempt count",
  );
}

const matrix = readJson(`${relativeEvaluatorRoot}/metric-decision-matrix.json`);
assert.equal(matrix.metrics.filter((metric) => metric.kind === "hard-gate").length, 4, "hard-gate count");
assert.equal(matrix.metrics.filter((metric) => metric.kind === "thresholded").length, 4, "thresholded metric count");
assert.equal(
  matrix.metrics
    .filter((metric) => metric.kind === "thresholded")
    .every((metric) => metric.threshold === "PENDING_MAINTAINER_DECISION"),
  true,
  "thresholds must remain pending until maintainer disposition",
);

const evaluatorManifest = validateEvaluatorManifest(evaluatorManifestPath);
assert.equal(evaluatorManifest.discussion_thread_ground_truth_used.length, 0, "unbound discussion ground truth");
assert.deepEqual(
  evaluatorManifest.sealed_members.map((member) => ({
    path: member.path,
    byte_length: member.byte_length,
    sha256: member.sha256,
  })),
  [
    {
      path: probeContract.sealed_payload.path,
      byte_length: probeContract.sealed_payload.byte_length,
      sha256: probeContract.sealed_payload.sha256,
    },
  ],
  "public probe commitment must match the sealed evaluator member",
);

process.stdout.write(
  `${JSON.stringify(
    {
      result: "PASS",
      mode: requestedMode,
      input_members: inputManifest.members.length,
      input_bundle_sha256: inputManifest.bundle_identity.bundle_sha256,
      regulatory_sections: census.sections.length,
      capture_units: captures.length,
      calibration_quotes: quoteCount,
      calibration_claims: claimCount,
      public_evaluator_members: evaluatorManifest.members.length,
      sealed_evaluator_members: evaluatorManifest.sealed_members.length,
      evaluator_bundle_sha256: evaluatorManifest.bundle_identity.bundle_sha256,
      evaluator_manifest_sha256: sha256(evaluatorManifestPath),
    },
    null,
    2,
  )}\n`,
);
