# AGENTS.md

Working rules for anyone — human or agent — changing this repository.
These are not suggestions. Anything below the line is a hard stop.

## The contract

The tool prints a score and an evidence line for every judgment. That means
every number here is falsifiable by a stranger. Treat that as the product:
a wrong check is worse than a missing check.

MUST NOT change a weight without a CHANGELOG entry explaining which real
repository justified it. Weights are the opinion of this tool; undocumented
opinion drift makes every past score incomparable.

NEVER merge a check that cannot show its evidence. If a check has no line
to print, it is a vibe, and vibes do not belong in a scorecard.

DO NOT add a network call. The whole promise is that the code is read on the
runner and never leaves it. One fetch destroys that promise and cannot be
walked back once someone notices.

MUST NOT execute scanned code. Not `import`, not `subprocess`, not a "safe"
sandbox. Reading text is the only permitted interaction with a target repo.

NEVER read outside the scanned directory. Path traversal in a scanner is a
remote file read from a stranger's repository.

DO NOT introduce a dependency. Zero dependencies is why this runs on any
runner in three seconds and why nobody has to audit our supply chain.

MUST keep `walk()` sorted. Unsorted traversal makes the same repository score
differently on Windows and Linux, and C2 samples the first 200 test files.

NEVER let a check silently return 10 for an error. A crash scored as a pass
is the exact failure this tool exists to find.

DO NOT weaken a test to make a build green. Fix the check, or delete it and
say so in the CHANGELOG.

MUST run `gate.sh` before every release tag, and paste its output into the
release notes.

NEVER tag a release with a failing self-test. The self-test workflow is the
public proof that the numbers work.

## What counts as done

`gate.sh` exits 0, the self-test workflow is green on `main`, and the run
page shows a non-empty scorecard. A local pass with a blank run page is
not done — that is the false green we sell against.
