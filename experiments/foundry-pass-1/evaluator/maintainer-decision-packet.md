# Foundry Pass 1: Maintainer Pre-Run Decision Packet

Status: READY FOR MAINTAINER DISPOSITION; execution is not authorized.

Prepared against experiment-brief commit
`789c93cf6d1fc0c4d136b77236a1c7d43f966655`.

This packet authorizes no compiler execution by itself. It records the
decisions required after the evaluator artifacts are content-bound and before
the graded run begins.

## Materials to disposition

The evaluator materials are bound by:

- evaluator manifest path:
  `experiments/foundry-pass-1/evaluator/evaluator-bundle-manifest.json`;
- evaluator manifest sha256:
  `dcd448e615bf197c463c8bed7fbb7e18a9c0dbf3b61bf9560b99eaafa04f8ea3`;
- logical evaluator-bundle sha256:
  `d00e04d48f8ebd681007d998b67cea10e1e9651b48c35f9fa22107ab3c923184`;
- logical closed-input-bundle sha256:
  `2388bd3ef8ff4a7cf3dfdb72a2567a0ef374fd33cb5af08ef50b5df227ab2c61`;
- sealed probe-oracle sha256:
  `285d5e5a7abfc3c757edb8aaeae35d6941c41cc1312b0bca2078c49d27254ae6`.

The evaluator-bundle manifest binds exact paths, byte lengths, and sha256
digests for:

- the input manifest and ingestion-job declaration;
- the independent census oracle;
- the public probe contract and the commitment to every sealed mutation and
  failure-probe oracle;
- the 17-page decomposition rubric;
- the challenge-question rubric;
- the metric-decision matrix; and
- the two stable calibration pages, page-plan ground truth, and challenge
  bank used by the evaluator.

The public PR intentionally excludes the sealed `probe-oracles.json` bytes.
The pipeline builder reviews only the public probe contract, invariant,
consequence, commitment, and reveal rule. Before execution authorization, the
maintainer separately receives the sealed file, verifies its byte length and
sha256, reviews its complete contents, and records a disposition. The exact
sealed bytes are revealed on the experiment branch only after graded outputs
are fixed and must match the pre-run commitment before scoring.

The maintainer decision must cite the evaluator-manifest and sealed-probe
sha256 values above.
Approval of an earlier filename, working-tree state, or positional "latest"
reference is not sufficient.

## Recommended binding thresholds

| Decision | Recommendation | Consequence if missed |
| --- | --- | --- |
| Median review duration | At or below 10 minutes | No workable-median throughput claim; revise packet or batching. |
| Maximum review duration | At or below 25 minutes | Pause scaling and inspect the slow packet. |
| Material ambiguities per reviewer packet | At or below 3 | Packet is not counted as dispositionable; pause it for diagnosis. |
| Material ambiguities per source section | Pause when above 10 | Pause the section for diagnosis; do not declare the normalization design invalid. |

These thresholds apply only to the measured Pass 1 sample. They are not
sector-wide service levels.

## Maintainer dispositions required

1. Accept, revise, or reject each recommended threshold.
2. Confirm that the maintainer will independently disposition the complete
   evaluator truth set, including the locally delivered sealed probe oracle,
   or name a separate reviewer for specified artifacts.
3. Confirm reviewer capacity for a maximum work-in-progress of five candidate
   pages, with no batch approval.
4. After the bound materials are accepted, give or withhold final execution
   authorization for the non-production measured pass.

A concise conforming decision may state:

> I disposition evaluator manifest
> `dcd448e615bf197c463c8bed7fbb7e18a9c0dbf3b61bf9560b99eaafa04f8ea3`
> and sealed probe oracle
> `285d5e5a7abfc3c757edb8aaeae35d6941c41cc1312b0bca2078c49d27254ae6`.
> I accept the four recommended thresholds, will disposition the complete
> truth set, confirm capacity for WIP 5 with no batch approval, and authorize
> the non-production measured pass.

Any revision must name the changed threshold or delegated review artifact
explicitly. Authorization remains withheld until the revised artifacts, if
any, are rebound and cited.

## Authorization boundary

Even after authorization, generated content remains quarantined. The pass
cannot promote pages, alter ratified schemas, claim RFC 005 conformance, or
make claims beyond its dispositioned measurements.
