// Schema-check every verified-answer/v0.1 envelope in a directory with the
// repo's locked AJV. Also recomputes each integrity.artifact_sha256 over the
// canonical bytes (sorted keys, no whitespace, artifact_sha256 removed).
// Usage: node tools/check_envelopes.mjs <dir>
import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dir = process.argv[2];
if (!dir) { console.error("usage: check_envelopes.mjs <dir>"); process.exit(2); }
const ajv = new Ajv2020({ allErrors: true, strict: true });
addFormats(ajv);
ajv.addSchema(JSON.parse(fs.readFileSync(path.join(root, "schemas/verified-answer-v0.1.schema.json"), "utf8")));
const validate = ajv.getSchema("urn:dwtc:schema:verified-answer:v0.1");

function canonical(value) {
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  if (value && typeof value === "object") {
    return "{" + Object.keys(value).sort().map((k) => JSON.stringify(k) + ":" + canonical(value[k])).join(",") + "}";
  }
  return JSON.stringify(value);
}

let checked = 0, failed = 0;
for (const name of fs.readdirSync(dir).filter((n) => n.endsWith(".json")).sort()) {
  const env = JSON.parse(fs.readFileSync(path.join(dir, name), "utf8"));
  checked += 1;
  const problems = [];
  if (!validate(env)) problems.push(ajv.errorsText(validate.errors, { separator: "; " }));
  const copy = structuredClone(env);
  delete copy.integrity.artifact_sha256;
  delete copy.integrity.signature;
  const digest = createHash("sha256").update(canonical(copy), "utf8").digest("hex");
  if (digest !== env.integrity.artifact_sha256) problems.push(`integrity digest mismatch (${digest})`);
  if (problems.length) { failed += 1; console.log(`FAIL ${name}: ${problems.join(" | ")}`); }
}
console.log(`envelopes checked: ${checked}, failed: ${failed}`);
process.exit(failed ? 1 : 0);
