# PR #6 re-review draft (do not post without maintainer word)

## CC adversarial re-review of 9abbce2: all five dispositions verified; recommend merge

Ari, I re-reviewed the revised branch (`3af4fff`, review-fix `9abbce2`) the same way I reviewed the original: executable probes against the checker's own validators, not a reading of the test names. Suite reproduction first: clean `npm ci`, foundation 7 schemas / 40 cases unchanged, amendment 5 schemas / 36 executable cases green, 5 integration cases honestly `specified`, matching your validation summary exactly.

Four independent probes, all constructed fresh rather than replaying your acceptance mutations, all rejected for the pinned reason:

1. **F1 verified structurally.** I built my own three-transition fallback traversal from the contract topology (`structured-to-prose`, `prose-to-validation`, `validation-to-backed`, orders 2, 4, 6) with `fallback.authorized` false and a rebound integrity digest. Rejected with "Fallback-marked traversal is not authorized by the audit." The code derives fallback use from the resolved contract's transition classifications; the fixture-specific comparison is gone as claimed.

2. **F2 verified on the family your cases do not cover.** AT-077 exercises the claim family and AT-078 the quote family. My probe overlapped an allowed alternative and the forbidden selection in `cell_ids`, with case-review payloads and manifest integrity rebound so the adversarial condition is what gets judged. Rejected with the per-ID message. Disjointness genuinely runs independently across all three families, for required and every alternative.

3. **F3 verified past AT-080's boundary.** AT-080 tests an undeclared gate; my probe used a *declared* control with an incompatible kind (a `policy-gate` control recorded as a `clarification` gate). Rejected with "has incompatible kind." The vocabulary resolution checks kind compatibility, not just existence.

4. **F5 verified against the quiet-shrink attack.** My probe retired an active capability case properly (prior accepted disposition preserved, terminal `retired` disposition appended, digests rebound) without replacing it, dropping the pool to 9 against a declared minimum of 10. Rejected with the bounds message. Retirement cannot masquerade as rotation, and the bounds count only active cases.

**F4 confirmed by inspection:** zero occurrences of `readerView` remain in the checker, and AT-069 stays honestly `specified` pending a process-level runner.

Two minor findings, neither blocking:

- **29 of 36 mutations carry no `expected_error` pin** (AT-041 through AT-068 plus AT-074). The wrong-reason guard only engages when the pin is present, so those cases could in principle pass on an unrelated failure after a future refactor. AT-075 through AT-081 all carry pins, which is the right discipline; recommend backfilling the other 29 in a follow-up, not as a condition of this merge.
- **Stale assertion message:** the manifest-order check's message still says "AT-041 through AT-074" while the logic correctly expects through AT-081. Cosmetic.

Verdict: all five findings are fixed as described, the fixes survive independent adversarial probes, and the branch is synchronized with main. **Recommend ratify and merge.** My probe harness is preserved uncommitted at `tests/acceptance/probe-cc-rereview.mjs` in my review worktree for reproduction.

CC
