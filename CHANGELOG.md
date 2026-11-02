# Changelog

Every weight change gets a line here, and every line names the repository that
justified it. If a score from last month is not comparable to today's, that is a
breaking change and it says so.

## 1.0.0 — 2026-11-03

First public release.

- Seven static checks: scope containment, false-green detection, drift
  containment, memory integrity, delivery gate, complexity control,
  regression surface.
- Composite Action, zero dependencies, Python 3.8+.
- `fail-under` input so the check can act as a merge gate rather than a report.
- Checks that do not apply return `n/a` and score 10 without dragging the total
  down. A library with no agent memory to audit should not be punished for it.
- `walk()` sorts directory and file traversal. Without this the same repository
  scores differently on Windows and Linux, because C2 samples the first 200 test
  files and C6 takes the largest source files.
- Weights: C1 18%, C2 18%, C5 16%, C3 14%, C6 12%, C7 12%, C4 10%.

### Why the weights sit where they do

C1 and C2 carry the most because they are the two failures that produce a green
build with wrong behaviour: an agent that can push anything, and tests that
cannot fail. C5 is next because "done" being self-declared is what an agent
optimises for. C4 is lowest because a repository with no cross-session state has
nothing to measure, and the check already returns `n/a`.

### Known limitations

- C6 uses file size as a proxy for context truncation. It is a proxy, not a
  measurement. A 3,000-line generated file scores worse than a 900-line file
  that is actually unreadable.
- C7 looks for a dependency lock and for tests that import each top-level
  module. It cannot tell whether those tests assert anything meaningful — that
  is C2's job, and C2 itself only counts assertions.
- Precision is unknown. No labelled corpus yet. False positives are tracked as
  issues, not fixed by quietly loosening a threshold.
