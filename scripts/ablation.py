"""Change-notes ablation: same 18 cases with incident-specific notes removed."""
import json, glob, collections, os
from pipebench.harness import Case, parse_response
TIERS = ["haiku", "sonnet", "opus"]
# incidents where the change note is the only evidence of the semantic change,
# so escalating without it is a defensible (not unnecessary) decision
NOTE_ONLY = {"F3b", "F5c", "H3"}
ab = {"resolved": "R", "wrong_data": "W", "failed_fix": "F", "rejected_unsafe": "X", "unsafe_fix": "U",
      "unnecessary_escalation": "e", "correct_escalation": "E", "invalid_response": "?"}
cases = sorted(os.path.basename(f)[:-5][3:] for f in glob.glob("runs/haiku/NN-*.json"))
res = {}
for cid in cases:
    iid, s = cid.rsplit("-s", 1); c = Case(iid, int(s))
    for t in TIERS:
        for cond, name in (("notes", cid), ("none", "NN-" + cid)):
            d = json.load(open(f"runs/{t}/{name}.json"))
            res[(t, cond, cid)] = c.evaluate(parse_response(d["raw_response"]))["outcome"]
os.makedirs("results/ablation", exist_ok=True)
L = ["| Incident | haiku notes/none | sonnet notes/none | opus notes/none |", "|---|---|---|---|"]
for iid in sorted({c.rsplit('-s', 1)[0] for c in cases}):
    cells = []
    for t in TIERS:
        a = "".join(ab[res[(t, "notes", f"{iid}-s{s}")]] for s in (1, 2))
        b = "".join(ab[res[(t, "none", f"{iid}-s{s}")]] for s in (1, 2))
        cells.append(f"{a} / {b}")
    L.append(f"| {iid}{'*' if iid in NOTE_ONLY else ''} | " + " | ".join(cells) + " |")
L.append("\n| Tier | cond | resolved | correct esc | harmful | unnecessary esc | acceptable esc (note-only) |")
L.append("|---|---|---|---|---|---|---|")
for t in TIERS:
    for cond in ("notes", "none"):
        c = collections.Counter(res[(t, cond, x)] for x in cases)
        acc = sum(1 for x in cases if res[(t, cond, x)] == "unnecessary_escalation" and x.split("-s")[0] in NOTE_ONLY)
        L.append(f"| {t} | {cond} | {c['resolved']} | {c['correct_escalation']} | {c['wrong_data']+c['unsafe_fix']} | "
                 f"{c['unnecessary_escalation']} | {acc} |")
open("results/ablation/tables.md", "w").write("\n".join(L) + "\n")
json.dump({f"{k[0]}|{k[1]}|{k[2]}": v for k, v in res.items()}, open("results/ablation/outcomes.json", "w"), indent=1)
print("\n".join(L))
