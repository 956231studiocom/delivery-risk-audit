#!/usr/bin/env bash
# Local delivery gate. Run this before every tag.
# Any non-zero exit means do not release.
set -uo pipefail
cd "$(dirname "$0")" || exit 2
FAIL=0

say() { printf '%s\n' "$*"; }

say "== 1/5 syntax =="
for f in audit.py entrypoint.py tests/test_audit.py e2e/test_entrypoint.py; do
  if python3 -m py_compile "$f" 2>/dev/null; then
    say "   ok   $f"
  else
    say "   FAIL $f"
    FAIL=1
  fi
done

say "== 2/5 unit tests =="
if python3 -m unittest discover -s tests -p "test_*.py" > /tmp/gate_unit.log 2>&1; then
  say "   ok   $(grep -Eo 'Ran [0-9]+ tests' /tmp/gate_unit.log | head -1)"
else
  say "   FAIL unit tests"
  tail -20 /tmp/gate_unit.log
  FAIL=1
fi

say "== 3/5 end-to-end =="
if python3 -m unittest discover -s e2e -p "test_*.py" > /tmp/gate_e2e.log 2>&1; then
  say "   ok   $(grep -Eo 'Ran [0-9]+ tests' /tmp/gate_e2e.log | head -1)"
else
  say "   FAIL end-to-end"
  tail -20 /tmp/gate_e2e.log
  FAIL=1
fi

say "== 4/5 determinism =="
# Write inside the repo: /tmp is not reliably writable from every shell that
# runs this gate, and a silent write failure reads as a score of ''.
python3 audit.py . --json .gate_d1.json --quiet >/dev/null 2>&1
python3 audit.py . --json .gate_d2.json --quiet >/dev/null 2>&1
A=$(python3 -c "import json;print(json.load(open('.gate_d1.json'))['total_score'])" 2>/dev/null)
B=$(python3 -c "import json;print(json.load(open('.gate_d2.json'))['total_score'])" 2>/dev/null)
if [ -n "$A" ] && [ "$A" = "$B" ]; then
  say "   ok   two runs agree: $A"
else
  say "   FAIL scores differ: '$A' vs '$B'"
  FAIL=1
fi

say "== 5/5 manifest =="
for f in action.yml README.md LICENSE CHANGELOG.md AGENTS.md audit.py entrypoint.py; do
  if [ -f "$f" ]; then say "   ok   $f"; else say "   FAIL missing $f"; FAIL=1; fi
done
if grep -q "using: 'composite'" action.yml && grep -q "entrypoint.py" action.yml; then
  say "   ok   action.yml wires the entrypoint"
else
  say "   FAIL action.yml does not wire the entrypoint"
  FAIL=1
fi

rm -f .gate_d1.json .gate_d2.json audit-report.md audit-report.json
if [ "$FAIL" -eq 0 ]; then
  say ""
  say "GATE PASS"
else
  say ""
  say "GATE FAIL"
fi
exit "$FAIL"
