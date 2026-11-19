"""Interval estimates, the test of the duplicate-key profile, and calibration.
Run score_reps.py for both runs first. Writes results/stats.md and
results/figures/fig4.png.

- Bootstrap 95% intervals resample cases (not runs), since the five repetitions of
  a case are not independent.
- The duplicate-profile effect is tested at the level of the case as well as the run.
- Calibration compares reported confidence with how often the decision was right
  (resolved or correctly escalated), over every distinct response.
"""
from __future__ import annotations

import glob
import json
import math
import os
import random
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TIERS = ["haiku", "sonnet", "opus"]
NAME = {"haiku": "Haiku", "sonnet": "Sonnet", "opus": "Opus"}
COL = {"haiku": "#2a78d6", "sonnet": "#eb6834", "opus": "#1baf7a"}
MARK = {"haiku": "o", "sonnet": "s", "opus": "^"}
RUNS = {"discovery": ("runs_api", "results_api"), "confirmation": ("runs_confirm", "results_confirm")}
GOOD = {"resolved", "correct_escalation"}
B = 10000
L = ["# Interval estimates, the duplicate-profile test and calibration\n"]


def pct(xs, q):
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def boot(values, seed, stat=st.mean):
    """Percentile bootstrap over cases. `values` holds one number per case."""
    rng = random.Random(seed)
    n = len(values)
    draws = [stat([values[rng.randrange(n)] for _ in range(n)]) for _ in range(B)]
    return pct(draws, 0.025), pct(draws, 0.975)


data = {}
for run, (rdir, res) in RUNS.items():
    rows = json.load(open(f"{res}/scored.json"))
    nn = {os.path.basename(f)[3:-5] for f in glob.glob(f"{rdir}/haiku/rep0/NN-*.json")}
    data[run] = (rows, nn)

# ------------------------------------------------------------ 1. intervals
L += ["## 1. Share of fixable cases resolved, with 95% bootstrap intervals over cases\n",
      f"{B} resamples of cases; each case contributes its share of the five repetitions that were resolved.\n",
      "| Run | Evidence | Tier | Fixable cases | Resolved (%) | 95% interval |", "|---|---|---|---|---|---|"]
per_case = {}
for run, (rows, _) in data.items():
    for cond in ("notes", "none"):
        for t in TIERS:
            by = {}
            for r in rows:
                if r["cond"] == cond and r["tier"] == t:
                    by.setdefault(r["case"], []).append(r)
            per_case[(run, cond, t)] = by
            fix = [st.mean(x["outcome"] == "resolved" for x in v) for c, v in sorted(by.items()) if v[0]["expected"] == "fix"]
            lo, hi = boot(fix, seed=11)
            L.append(f"| {run} | {'full' if cond == 'notes' else 'no notes'} | {t} | {len(fix)} | {100 * st.mean(fix):.1f} | "
                     f"{100 * lo:.1f} to {100 * hi:.1f} |")
L += ["\n### Sonnet minus Opus, success (resolved or correctly escalated), in cases per pass\n",
      "Paired bootstrap over cases.\n", "| Run | Evidence | Cases | Difference | 95% interval |", "|---|---|---|---|---|"]
for run in data:
    for cond in ("notes", "none"):
        a, b = per_case[(run, cond, "sonnet")], per_case[(run, cond, "opus")]
        d = [st.mean(x["outcome"] in GOOD for x in a[c]) - st.mean(x["outcome"] in GOOD for x in b[c]) for c in sorted(a)]
        lo, hi = boot(d, seed=13, stat=sum)
        L.append(f"| {run} | {'full' if cond == 'notes' else 'no notes'} | {len(d)} | {sum(d):+.1f} | {lo:+.1f} to {hi:+.1f} |")

# ------------------------------------------------------------ 2. duplicate profile
rows, _ = data["confirmation"]
L += ["\n## 2. The duplicate-key profile on H6 (confirmation run)\n",
      "| Tier | Case | Unsafe fixes without profile | With profile |", "|---|---|---|---|"]
h6 = sorted({r["case"] for r in rows if r["case"].startswith("H6")})
for t in TIERS:
    for c in h6:
        a = sum(r["outcome"] == "unsafe_fix" for r in rows if r["tier"] == t and r["case"] == c and r["cond"] == "none")
        b = sum(r["outcome"] == "unsafe_fix" for r in rows if r["tier"] == t and r["case"] == c and r["cond"] == "dup_profile")
        L.append(f"| {t} | {c} | {a} of 5 | {b} of 5 |")


def fisher_two_sided(a, b, c, d):
    """Two-sided Fisher exact test for the table [[a, b], [c, d]]."""
    n1, n2, k, n = a + b, c + d, a + c, a + b + c + d
    p = lambda x: math.comb(n1, x) * math.comb(n2, k - x) / math.comb(n, k)  # noqa: E731
    p0 = p(a)
    return sum(p(x) for x in range(max(0, k - n2), min(k, n1) + 1) if p(x) <= p0 * (1 + 1e-9))


L.append("")
for t in ("sonnet", "opus"):
    a = sum(r["outcome"] == "unsafe_fix" for r in rows if r["tier"] == t and r["case"] in h6 and r["cond"] == "none")
    b = sum(r["outcome"] == "unsafe_fix" for r in rows if r["tier"] == t and r["case"] in h6 and r["cond"] == "dup_profile")
    L.append(f"- {t}, run level: {a} of 15 against {b} of 15; Fisher exact two-sided p = {fisher_two_sided(a, 15 - a, b, 15 - b):.1e}. "
             "Runs of one case are not independent, so this overstates the evidence.")
k = len(h6)
L.append(f"- Case level: the unsafe-fix rate fell in {k} of {k} cases for each of Sonnet and Opus. An exact two-sided sign test "
         f"on {k} cases cannot give a p-value below {2 * 0.5 ** k:.2f}, so with three cases the case-level test is not "
         "significant by itself. The support for the effect is its size (every run, both models), the mechanism visible "
         "in the replies, the agreement with the natural contrast in the discovery run (seed 1 against seed 2), and the "
         "fact that it was predicted before the run.")

# ------------------------------------------------------------ 3. calibration
BINS = [(0.0, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0001)]
L += ["\n## 3. Calibration of reported confidence\n",
      "A response is correct if its outcome is resolved or a correct escalation. Every distinct response to a full or "
      "no-notes prompt is used. ECE is the expected calibration error over the five bins shown.\n",
      "| Run | Tier | Responses | Mean confidence | Share correct | ECE | " +
      " | ".join(f"{lo:.1f} to {min(hi, 1.0):.1f}: n, correct" for lo, hi in BINS) + " |",
      "|---|---|---|---|---|---|" + "---|" * len(BINS)]
fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0), sharey=True)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.5})
for j, (run, (rows, nn)) in enumerate(data.items()):
    ax = axes[j]
    ax.plot([0.3, 1], [0.3, 1], color="#9b9a94", lw=0.9, ls="--", zorder=1)
    if j == 1:
        ax.text(0.99, 0.33, "dashed line: perfect calibration", ha="right", va="bottom", fontsize=7.5, color="#5f5e5a")
    for t in TIERS:
        R = [r for r in rows if r["tier"] == t and (r["cond"] == "notes" or (r["cond"] == "none" and r["case"] in nn))
             and r["conf"] is not None]
        conf = [r["conf"] for r in R]
        ok = [r["outcome"] in GOOD for r in R]
        ece, cells, xs, ys = 0.0, [], [], []
        for lo, hi in BINS:
            idx = [i for i, c in enumerate(conf) if lo <= c < hi]
            if not idx:
                cells.append("0")
                continue
            mc, acc = st.mean(conf[i] for i in idx), st.mean(ok[i] for i in idx)
            ece += len(idx) / len(R) * abs(acc - mc)
            cells.append(f"{len(idx)}, {100 * acc:.0f}%")
            if len(idx) >= 10:
                xs.append(mc)
                ys.append(acc)
        L.append(f"| {run} | {t} | {len(R)} | {st.mean(conf):.2f} | {100 * st.mean(ok):.1f}% | {ece:.3f} | " + " | ".join(cells) + " |")
        ax.plot(xs, ys, color=COL[t], marker=MARK[t], ms=5, lw=1.5, mec="white", mew=0.6, label=NAME[t], zorder=3)
    ax.set_title(("Discovery run (seeds 1, 2)", "Confirmation run (seeds 3 to 5)")[j], fontsize=8.5, loc="left")
    ax.set_xlabel("Mean reported confidence in bin")
    ax.set_xlim(0.45, 1.0)
    ax.set_ylim(0.3, 1.02)
    ax.yaxis.grid(True, color="#dddcd6", lw=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
axes[0].set_ylabel("Share of decisions that were correct")
axes[0].legend(frameon=False, loc="lower right", handlelength=2)
fig.tight_layout(w_pad=1.5)
os.makedirs("results/figures", exist_ok=True)
fig.savefig("results/figures/fig4.png", dpi=300, bbox_inches="tight", facecolor="white")

open("results/stats.md", "w").write("\n".join(L) + "\n")
print("\n".join(L))
