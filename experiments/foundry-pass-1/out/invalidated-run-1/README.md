# Invalidated extraction run 1 (2026-08-02, pre-dawn)

All 38 sections were extracted through role sessions whose context was
contaminated by ambient session configuration: the interactive-session
SessionStart hook injected identity-anchor content, and the CLI natively
injected global CLAUDE.md/memory context. The declared bundle-only boundary
was therefore violated in context (never in access: tools were disabled and
no file reads occurred). Detected because five role sessions narrated the
foreign content instead of producing strict JSON; confirmed by leak probes.

Disposition: run invalidated in full, no extraction-quality claim made from
it; outputs preserved here as failure-record evidence per the no-purge
principle. Fix: CC_ANCHOR_BYPASS_ROLE_SESSION guard in the hook plus
--setting-sources "" on every role invocation, both leak-probe verified
CLEAN before run 2.
