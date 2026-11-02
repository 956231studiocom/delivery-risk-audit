# AI Delivery Risk Audit

Seven static checks for repositories that an AI agent writes to. Scores in seconds, prints an evidence line for every judgment, and never runs your code.

```yaml
- uses: 956231studiocom/delivery-risk-audit@v1
```

That is the whole setup. The scorecard appears on the workflow run page, and `audit-report.md` lands in your workspace.

---

## What it actually measures

Not "is this code good". **Is this repository safe to hand to an agent, and can you tell when it broke something.**

| # | Check | Weight | What scores zero |
|---|---|---|---|
| C1 | Scope Containment | 18% | An agent can edit any file and push it with nothing in the way |
| C2 | False-Green Detection | 18% | Tests that cannot fail — no e2e layer, assertions that pass on empty output |
| C5 | Delivery Gate | 16% | "Done" is self-declared, with no hard criterion for finished |
| C3 | Drift Containment | 14% | Constraints live in someone's memory, not in a file the agent re-reads |
| C6 | Complexity Control | 12% | Files so large the agent's context truncates mid-edit |
| C7 | Regression Surface | 12% | Nothing marks which behaviour is supposed to stay identical |
| C4 | Memory Integrity | 10% | No state anchor across sessions — the same question gets contradictory answers |

A check that does not apply is marked **n/a** and does not drag the total down. A library that never pins dependencies is not committing a defect; C3 simply has nothing to say about it. The tool says so instead of inventing a verdict.

## A real run

```
tiangolo/fastapi   65.4 / 100   High    3,235 files
  C1 Scope Containment        8/10    CI config .github/workflows
  C2 False-Green Detection    8/10    source 1223 / test 693 (ratio 56.7%)
  C3 Drift Containment        0/10    no constraint files found
  C5 Delivery Gate            8/10
  C6 Complexity Control       4/10    oversized files
  C7 Regression Surface      10/10
  C4 Memory Integrity         7/10
```

FastAPI is a mature library, and it scores High — because C3 and C6 are asking questions that suit an **agent-maintained application**, not a hand-written library. Read the evidence lines, not the headline number. That is the point of printing them.

## It found its own gaps

The first time this tool ran on its own repository, it scored **30.6 / Severe**.

```
C2 False-Green Detection   0/10   no test directory, no e2e layer
C3 Drift Containment       0/10   no constraint file found
C5 Delivery Gate           2/10   no gate script, no release record
C7 Regression Surface      0/10   no dependency lock
```

None of those were surprises, and none of them were false positives. Fixing exactly what the evidence lines pointed at — tests, an e2e layer, `AGENTS.md` with hard prohibitions, a `gate.sh`, a changelog, a lock file — moved the same repository to **78.6 / Medium** without touching a single check or weight.

That is the intended loop: the score is not a grade you receive, it is a list of the next four things to fix. `examples/sample-report.md` is the unedited output of that second run.

## Why this and not a linter

A linter checks whether syntax and style hold. These checks ask whether the *delivery process* holds: who can push, whether a green build means anything, and whether "finished" is something a person decided or something the agent announced.

## Privacy

The checks are static. Your code is read, never executed, and never leaves the runner — the Action runs inside your own CI, on your own machine. Nothing is uploaded. There is no account, no token, no telemetry.

## Options

```yaml
- uses: 956231studiocom/delivery-risk-audit@v1
  with:
    path: '.'
    fail-under: '70'        # fail the step below this score; omit to always pass
    markdown: 'true'        # writes audit-report.md
    report-path: 'audit-report.md'
```

Outputs: `score`, `grade`, `report`, `json`.

## Run it locally

```bash
python3 audit.py . --md report.md --json report.json
```

Zero dependencies. Python 3.8+.

## What this is not

- Not a penetration test.
- Not a SonarQube replacement — it does not parse your AST or count code smells.
- Not a guarantee. It is seven checks with published weights, and you can re-run every one of them yourself.

---

If you want the full written report with a fix order, or a person to read it and walk you through it: [956231studio.com/ai-code-audit](https://956231studio.com/ai-code-audit/)

MIT licensed. Issues and false positives are welcome — a check that misfires on your repo is a bug worth fixing.
