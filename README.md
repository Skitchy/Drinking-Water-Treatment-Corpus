# Drinking Water Treatment Corpus

An open, verified knowledge base for drinking water treatment, built in the [Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog).

## Status: RFC / design phase

Nothing is ingested yet, deliberately. Two design proposals are open for review and adversarial critique in [Discussions](../../discussions):

1. **The Corpus**: a repository of small, single-topic markdown pages where every regulatory quote is machine-verified against an authoritative source on a schedule, every page carries its provenance in the open, and a named human domain expert signs the page list.
2. **The Reader**: a serving layer that actually honors OKF v0.2 trust signals at retrieval time (status gating, staleness refusal, trust-tier ranking) and mechanically verifies model answers against retrieved pages before a human sees them.

Devil's advocacy is invited on both. The designs are only as good as the strongest objection they survive.

## The idea in one paragraph

Text anyone can generate now. Text you can **audit** is the scarce thing. Every page in this corpus separates a quoted layer (verbatim source text, character-verified against the official record, re-verified by CI on a schedule) from an editorial layer (plain-English context with a named, credentialed human behind it). When a regulation changes, affected pages flip to review status automatically and visibly. Public domain and expressly licensed sources only; the exclusion list is published. A utility, a student, or an AI system that clones this repo gets knowledge it can check, not just knowledge it can read.

## Sources (planned, license-gated)

US federal works (public domain, 17 USC §105): EPA Drinking Water Rule Quick Reference Guides, 40 CFR Part 141 via the eCFR point-in-time API, NIOSH chemical safety entries, and more. State layer: California Title 22 drinking water chapters and Ten States Standards (reproduced with credit per its own published permission). Copyrighted materials (AWWA, commercial textbooks, WHO guidelines) are excluded and cited only. Full licensing analysis is in the corpus RFC.

## Maintainer

Jason "Skitch" Wiltsey, Water Treatment Operator III. This project is part of the Operator's Workshop at [H2oCareerPro.com](https://www.h2ocareerpro.com), where the builds behind it are documented in public.

## Licensing (planned)

Quoted federal text: public domain. Editorial content: CC BY 4.0. Tooling: MIT. Formal LICENSE files land when the first pages do.
