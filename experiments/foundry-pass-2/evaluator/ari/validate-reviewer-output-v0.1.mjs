#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = process.env.DWTC_REPO_ROOT || process.cwd();
const requireFromRepo = createRequire(path.join(repoRoot, "package.json"));
const Ajv2020 = requireFromRepo("ajv/dist/2020").default;

const args = process.argv.slice(2);
const schemaPath = args.shift() || path.join(here, "reviewer-output-v0.1.schema.json");
if (args.length === 0) {
  console.error("usage: validate-reviewer-output-v0.1.mjs [schema] output.json [...]");
  process.exit(2);
}

const schema = JSON.parse(fs.readFileSync(schemaPath, "utf8"));
const ajv = new Ajv2020({ allErrors: true, allowUnionTypes: true, strict: true });
const validate = ajv.compile(schema);
let failed = false;

for (const outputPath of args) {
  const value = JSON.parse(fs.readFileSync(outputPath, "utf8"));
  const objects = Array.isArray(value) ? value : [value];
  for (const [index, object] of objects.entries()) {
    if (!validate(object)) {
      failed = true;
      console.error(`${outputPath}[${index}]: FAIL`);
      console.error(JSON.stringify(validate.errors, null, 2));
    }
  }
  if (!failed) console.log(`${outputPath}: PASS`);
}

process.exit(failed ? 1 : 0);
