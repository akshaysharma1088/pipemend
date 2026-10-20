"""Check that every fixable case is solved by its reference fix with no monitor
alerts, that escalation cases are scored correctly, and report the rule-based
self-healing (RBSH) baseline. Reference fixes were never shown to agents."""
import collections
import json
import os

from pipebench import rules
from pipebench.harness import Case
from pipebench.incidents import INCIDENTS
from pipebench.reference import REFERENCE

ok = True
rbsh = collections.Counter()
rows = []
for inc in INCIDENTS:
    for seed in (1, 2):
        c = Case(inc.iid, seed)
        r = c.evaluate(REFERENCE[inc.iid])
        want = "resolved" if inc.expected == "fix" else "correct_escalation"
        good = r["outcome"] == want and not r.get("gate_alerts")
        ok &= good
        b = rules.run(c)
        rbsh[b["policy_outcome"]] += 1
        rows.append({"case": c.case_id, "expected": inc.expected, "reference": r["outcome"],
                     "symptom": "error" if c.error else f"{len(c.alerts)} alerts", "rbsh": b["policy_outcome"]})
        print(f"{c.case_id:7s} {inc.expected:8s} reference={r['outcome']:18s} rbsh={b['policy_outcome']}")
os.makedirs("results", exist_ok=True)
json.dump(rows, open("results/validation.json", "w"), indent=1)
print("\nRBSH totals:", dict(rbsh))
print("ALL REFERENCE FIXES OK" if ok else "REFERENCE CHECK FAILED")
raise SystemExit(0 if ok else 1)
