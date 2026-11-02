#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Delivery Risk Audit - 7-Check Static Scanner
Runs seven static delivery-risk checks against any local code repository and emits a scorecard with evidence.
Principles: every judgment must carry a re-runnable evidence line; static only; read-only; the scanned code is never executed.
Usage: python3 audit.py <repo_path> [--name label] [--json out.json] [--md out.md] [--quiet]
"""
import argparse, json, os, re, sys
from datetime import datetime, timezone

SKIP_DIRS = {".git",".hg",".svn","node_modules","dist","build","__pycache__",".venv","venv","env",
".next",".nuxt","target","vendor",".idea",".vscode","coverage",".pytest_cache",".mypy_cache",
".tox","site-packages",".turbo",".cache","out","bin","obj",".gradle","htmlcov"}
CODE_EXT = {".py",".js",".jsx",".ts",".tsx",".go",".rs",".java",".kt",".rb",".php",".cs",".swift",
".c",".cc",".cpp",".h",".hpp",".m",".scala",".vue",".svelte"}
TEST_PAT = re.compile(r"(^test_.*\.py$)|(.*_test\.py$)|(.*\.test\.[jt]sx?$)|(.*\.spec\.[jt]sx?$)|(^tests?$)|(^__tests__$)|(^testdata$)", re.I)
TEST_DIR_SEG = {"test","tests","__tests__","testdata","e2e","integration_tests","testing"}
TEST_FILE_PAT = re.compile(r"(^test_.*\.py$)|(.*_test\.py$)|(.*\.test\.[jt]sx?$)|(.*\.spec\.[jt]sx?$)", re.I)


def is_test(rel):
    segs = os.path.normpath(rel).split(os.sep)
    if any(s.lower() in TEST_DIR_SEG for s in segs[:-1]):
        return True
    return bool(TEST_FILE_PAT.match(os.path.basename(rel)))


AGENT_MEM_FILES = ["AGENTS.md","CLAUDE.md","GEMINI.md",".cursorrules",".windsurfrules",
"copilot-instructions.md",".github/copilot-instructions.md","CONTRIBUTING.md","ARCHITECTURE.md"]
MEMORY_FILES = ["MEMORY.md",".memory","memory.json","memory.md",".agent/memory",".claude/memory","context.md","STATE.md"]
LOCK_FILES = ["package-lock.json","pnpm-lock.yaml","yarn.lock","bun.lockb","poetry.lock","Pipfile.lock",
"uv.lock","Cargo.lock","go.sum","composer.lock","Gemfile.lock","packages.lock.json","requirements.txt"]
CI_PATHS = [".github/workflows",".gitlab-ci.yml",".circleci/config.yml","azure-pipelines.yml","Jenkinsfile",".drone.yml"]
GATE_WORDS = re.compile(r"(gate|guard|fence|enforce|policy|lint-staged|pre-commit|required.?check|branch.?protect)", re.I)
FORBID_WORDS = re.compile(r"(MUST NOT|MUST|NEVER|禁止|不得|forbidden|DO NOT|do not)", re.I)


def walk(root):
    # 顺序必须确定：os.walk 的产出顺序依赖文件系统，同一仓库在 Windows 与 Linux 上
    # 会得到不同的 files 顺序，导致 C2 的 test[:200] 取样不同、分数漂移。
    files, dirs = [], []
    for cur, dnames, fnames in os.walk(root):
        dnames[:] = sorted(d for d in dnames if d not in SKIP_DIRS)
        rel_cur = os.path.relpath(cur, root)
        if rel_cur != ".":
            dirs.append(rel_cur)
        for f in sorted(fnames):
            files.append(os.path.normpath(os.path.join(rel_cur, f)) if rel_cur != "." else f)
    return sorted(files), sorted(dirs)


def read_text(path, limit=400_000):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except Exception:
        return ""


def count_lines(path):
    try:
        with open(path, "rb") as fh:
            return sum(1 for _ in fh)
    except Exception:
        return 0


def exists_any(root, rels):
    return [r for r in rels if os.path.exists(os.path.join(root, r))]


def ci_blob(root, limit=60_000):
    blob = ""
    for c in exists_any(root, CI_PATHS):
        p = os.path.join(root, c)
        if os.path.isdir(p):
            for fn in os.listdir(p):
                fp = os.path.join(p, fn)
                if os.path.isfile(fp):
                    blob += read_text(fp, limit)
        else:
            blob += read_text(p, limit)
    return blob


def c1(root, files, dirs):
    ev, score = [], 0
    ci = exists_any(root, CI_PATHS)
    ev.append("CI config: " + (", ".join(ci) if ci else "none found"))
    if ci:
        score += 3
    co = exists_any(root, ["CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"])
    if co:
        score += 2; ev.append("CODEOWNERS present: " + ", ".join(co))
    else:
        ev.append("CODEOWNERS: none (no gate on critical paths)")
    pre = exists_any(root, [".pre-commit-config.yaml", ".husky", ".git/hooks/pre-commit", "lefthook.yml"])
    if pre:
        score += 3; ev.append("Pre-commit hook: " + ", ".join(pre))
    else:
        ev.append("Pre-commit hook: none")
    if ci:
        if GATE_WORDS.search(ci_blob(root)):
            score += 2; ev.append("CI contains gate/guard/policy semantics: yes")
        else:
            ev.append("CI contains gate/guard/policy semantics: no")
    score = min(score, 10)
    note = "An agent can edit any file and push it with nothing in the way." if score <= 3 else ""
    return {"id":"C1","name":"Scope Containment","score":score,"weight":0.18,"evidence":ev,"note":note}


def c2(root, files, dirs):
    ev = []
    code = [f for f in files if os.path.splitext(f)[1].lower() in CODE_EXT]
    test = [f for f in files if is_test(f)]
    ratio = (len(test)/len(code)*100) if code else 0
    ev.append("Source files %d / test files %d (test ratio %.1f%%)" % (len(code), len(test), ratio))
    score = 0
    if ratio >= 40: score += 5
    elif ratio >= 20: score += 4
    elif ratio >= 8: score += 2
    elif ratio > 0: score += 1
    e2e = [d for d in dirs if re.search(r"(e2e|integration|acceptance|smoke)", d, re.I)]
    if e2e:
        score += 2; ev.append("E2E/integration layer: " + ", ".join(e2e[:4]))
    else:
        ev.append("E2E/integration layer: none (unit tests only - false green is likely)")
    cnt, sample = 0, test[:200]
    for tf in sample:
        cnt += len(re.findall(r"\b(assert|expect\(|should\.|t\.Error|require\.)", read_text(os.path.join(root, tf), 80_000)))
    per = cnt/max(len(sample),1)
    ev.append("Assertion density: %d assertions across %d test files (%.1f per file)" % (cnt, len(sample), per))
    if per >= 5: score += 2
    elif per >= 2: score += 1
    if re.search(r"(pytest|npm test|yarn test|pnpm test|go test|cargo test|jest|vitest|tox|nox)", ci_blob(root), re.I):
        score += 1; ev.append("CI runs the tests: yes")
    else:
        ev.append("CI runs the tests: none found")
    score = min(score, 10)
    note = "Tests prove it did not crash, not that the output is right. A green build with wrong output is the default agent failure." if score <= 3 else ""
    return {"id":"C2","name":"False-Green Detection","score":score,"weight":0.18,"evidence":ev,"note":note}


def c3(root, files, dirs):
    ev = []
    hits = exists_any(root, AGENT_MEM_FILES)
    ev.append("Agent constraint files: " + (", ".join(hits) if hits else "none found"))
    blob = ""
    for h in hits:
        p = os.path.join(root, h)
        if os.path.isdir(p):
            for fn in os.listdir(p):
                fp = os.path.join(p, fn)
                if os.path.isfile(fp):
                    blob += read_text(fp, 60_000)
        else:
            blob += read_text(p, 80_000)
    fw = len(FORBID_WORDS.findall(blob))
    if not hits: score = 0
    elif len(hits) == 1: score = 5
    else: score = 7
    if fw >= 10: score += 3
    elif fw >= 3: score += 2
    elif fw >= 1: score += 1
    ev.append("Constraint strength: %d hard prohibitions found (MUST / NEVER / forbidden)" % fw)
    if hits and fw == 0:
        ev.append("Constraint files describe practice but state no prohibitions - the agent has no absolute line")
    score = min(score, 10)
    note = "The constraints live in somebody's memory. In a long session the agent quietly redefines them." if score <= 4 else ""
    return {"id":"C3","name":"Drift Containment","score":score,"weight":0.14,"evidence":ev,"note":note}


def c4(root, files, dirs):
    ev = []
    mem = exists_any(root, MEMORY_FILES)
    agentic = any(re.search(r"(agent|llm|prompt|claude|openai|assistant|chat)", f, re.I) for f in files)
    ev.append("Memory/state files: " + (", ".join(mem) if mem else "none found"))
    ev.append("Project shows agent/LLM characteristics: %s" % ("yes" if agentic else "no"))
    if not agentic and not mem:
        ev.append("Not an agent project and no state memory - this check does not apply")
        return {"id":"C4","name":"Memory Integrity","score":10,"weight":0.10,"evidence":ev,"note":"","na":True}
    score = 4 if agentic else 0
    if mem: score += 5
    if agentic and not mem:
        ev.append("Note: agent project without cross-session memory files. Within a single session this is not a conflict; it becomes a gap the moment state is expected to persist")
    cf = [f for f in files if re.search(r"(dedup|conflict|reconcile|memory.*doctor|governor)", f, re.I)]
    if cf:
        score += 3; ev.append("Conflict arbitration: " + ", ".join(cf[:3]))
    else:
        ev.append("Conflict arbitration: none (no arbiter when old and new context disagree)")
    snap = [f for f in files if re.search(r"(memory|state)", os.path.basename(f), re.I) and re.search(r"(snapshot|archive|\.bak)", f, re.I)]
    if snap:
        score += 2; ev.append("Memory snapshots/archives: %d" % len(snap))
    score = min(score, 10)
    note = "No state anchor across sessions. The same question gets contradictory answers on different days." if score <= 4 else ""
    return {"id":"C4","name":"Memory Integrity","score":score,"weight":0.10,"evidence":ev,"note":note}


def c5(root, files, dirs):
    ev = []
    gf = [f for f in files if GATE_WORDS.search(os.path.basename(f))]
    ev.append("Gate scripts/config: " + (", ".join(gf[:6]) if gf else "none found"))
    score = 0
    if gf: score += 4
    if exists_any(root, CI_PATHS):
        score += 2; ev.append("CI present (may act as a required merge check)")
    ver = exists_any(root, ["CHANGELOG.md","CHANGELOG","HISTORY.md","RELEASE.md"])
    if ver:
        score += 2; ev.append("Release record: " + ", ".join(ver))
    tg = [f for f in files if re.search(r"(preflight|pre-commit|gate\.sh|check\.sh|verify)", os.path.basename(f), re.I)]
    if tg:
        score += 2; ev.append("Preflight/self-check scripts: " + ", ".join(tg[:4]))
    score = min(score, 10)
    note = "No hard criterion for finished. Completion is self-declared, which is exactly what an agent optimises for." if score <= 4 else ""
    return {"id":"C5","name":"Delivery Gate","score":score,"weight":0.16,"evidence":ev,"note":note}


def c6(root, files, dirs):
    ev = []
    code = [f for f in files if os.path.splitext(f)[1].lower() in CODE_EXT]
    sizes = sorted(((count_lines(os.path.join(root,f)), f) for f in code[:4000]), reverse=True)
    total = sum(s for s,_ in sizes); avg = total/len(sizes) if sizes else 0
    src_sizes = [x for x in sizes if not is_test(x[1])]
    src_huge = [x for x in src_sizes if x[0] > 800]
    huge = [x for x in sizes if x[0] > 800]; big = [x for x in sizes if 400 < x[0] <= 800]
    ev.append("Code files %d, total %s lines, mean %.0f lines/file" % (len(sizes), format(total, ","), avg))
    ev.append("Files over 800 lines: %d (business logic %d, tests %d); 400-800 lines: %d"
              % (len(huge), len(src_huge), len(huge)-len(src_huge), len(big)))
    if sizes[:3]:
        ev.append("Three largest files: " + "; ".join("%s (%d lines)" % (f, s) for s, f in sizes[:3]))
    n = len(src_huge) if len(src_huge) != len(huge) else len(huge)
    if n == 0: score = 10
    elif n <= 3: score = 7
    elif n <= 10: score = 4
    elif n <= 25: score = 2
    else: score = 1
    if avg > 400:
        score = max(1, score-2); ev.append("Mean above 400 lines/file: granularity too coarse overall")
    note = "Oversized files. The agent's context truncates mid-edit and the regression lands unseen." if score <= 4 else ""
    return {"id":"C6","name":"Complexity Control","score":score,"weight":0.12,"evidence":ev,"note":note}


def c7(root, files, dirs):
    ev = []
    locks = exists_any(root, LOCK_FILES)
    ev.append("Dependency lock: " + (", ".join(locks) if locks else "none (builds are not reproducible)"))
    score = 4 if locks else 0
    # Coverage: source package names vs packages actually imported by tests. No directory guessing.
    WRAP = ("src", "lib", "python", "packages", "pkg")
    mods = set()
    for f in files:
        if f.endswith(".py") and not is_test(f):
            segs = os.path.normpath(f).split(os.sep)
            i = 0
            while i < len(segs) - 1 and segs[i] in WRAP:
                i += 1
            if i < len(segs) - 1:
                mods.add(segs[i])
    touched = set()
    for f in files:
        if is_test(f) and f.endswith(".py"):
            txt = read_text(os.path.join(root, f), 120_000)
            for mm in re.finditer(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", txt, re.M):
                touched.add(mm.group(1).split(".")[0])
    hit = mods & touched
    cover = (len(hit) / len(mods) * 100) if mods else 0
    miss = sorted(mods - hit)[:8]
    ev.append("Source packages %d, reachable by test imports %d (coverage %.0f%%)%s"
              % (len(mods), len(hit), cover, ("; not covered: " + ", ".join(miss)) if miss else ""))
    if cover >= 70: score += 3
    elif cover >= 40: score += 2
    elif cover > 0: score += 1
    if cover >= 70: score += 3
    elif cover >= 40: score += 2
    elif cover > 0: score += 1
    if re.search(r"(matrix:|os:|node-version|python-version)", ci_blob(root), re.I):
        score += 3; ev.append("CI matrix across environments: yes")
    else:
        ev.append("CI matrix across environments: none (verified in one environment only)")
    score = min(score, 10)
    note = "One change, no way to enumerate the blast radius. Regression becomes luck instead of a checklist." if score <= 4 else ""
    return {"id":"C7","name":"Regression Surface","score":score,"weight":0.12,"evidence":ev,"note":note}


LEVELS = [(85, "Low"), (70, "Medium"), (50, "High"), (0, "Severe")]


def grade(total):
    for th, label in LEVELS:
        if total >= th:
            return label
    return "Severe"


def run(root, name=None):
    root = os.path.abspath(root)
    name = name or os.path.basename(root.rstrip(os.sep))
    files, dirs = walk(root)
    checks = [c1(root,files,dirs), c2(root,files,dirs), c3(root,files,dirs), c4(root,files,dirs),
              c5(root,files,dirs), c6(root,files,dirs), c7(root,files,dirs)]
    tw = sum(c["weight"] for c in checks)
    total = round(sum(c["score"]/10.0*(c["weight"]/tw)*100 for c in checks), 1)
    return {"tool":"AI Delivery Risk Audit","version":"1.0.0",
            "scanned_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "target":{"name":name,"path":root,"files":len(files),"dirs":len(dirs)},
            "total_score":total,"risk_level":grade(total),"checks":checks}


def to_markdown(r):
    L = ["# AI Delivery Risk Audit - %s" % r["target"]["name"], "",
         "**Score %s/100 - risk level: %s**" % (r["total_score"], r["risk_level"]), "",
         "Scanned %s | files %s | dirs %s" % (r["scanned_at"], r["target"]["files"], r["target"]["dirs"]), "",
         "## Scorecard", "", "| # | Check | Score | Weight | Verdict |", "|---|---|---|---|---|"]
    for c in r["checks"]:
        v = "pass" if c["score"] >= 8 else ("acceptable" if c["score"] >= 6 else "needs fixing")
        L.append("| %s | %s | %s/10 | %d%% | %s |" % (c["id"], c["name"], c["score"], int(c["weight"]*100), v))
    L += ["", "## Evidence", ""]
    for c in r["checks"]:
        L.append("### %s %s - %s/10" % (c["id"], c["name"], c["score"]))
        for e in c["evidence"]:
            L.append("- " + e)
        if c.get("note"):
            L.append("- **Risk:** " + c["note"])
        L.append("")
    gaps = [c for c in r["checks"] if c["score"] < 8 and not c.get("na")]
    L += ["## Priority stack", ""]
    if not gaps:
        L.append("All seven checks scored 8 or above. Nothing high priority.")
    else:
        gaps.sort(key=lambda c: (c["score"], -c["weight"]))
        for i, c in enumerate(gaps[:5], 1):
            L.append("%d. **%s (%s/10)** - %s" % (i, c["name"], c["score"], c.get("note") or "below threshold, address first."))
    L += ["", "---", "*Generated by seven static checks. Every judgment carries an evidence line you can re-run. Read-only: the scanned code is never executed.*"]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path"); ap.add_argument("--name", default=None)
    ap.add_argument("--json", default=None); ap.add_argument("--md", default=None)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    if not os.path.isdir(a.path):
        print("ERROR: not a directory: " + a.path, file=sys.stderr); return 2
    r = run(a.path, a.name)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(r, fh, ensure_ascii=False, indent=2)
    if a.md:
        with open(a.md, "w", encoding="utf-8") as fh:
            fh.write(to_markdown(r))
    if not a.quiet:
        print("%s: %s/100 (%s)" % (r["target"]["name"], r["total_score"], r["risk_level"]))
        for c in r["checks"]:
            print("  %s %-12s %2d/10" % (c["id"], c["name"], c["score"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
