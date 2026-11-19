"""Draw the paper's figures from the scored runs. Writes results/figures/fig1.png
(benchmark flow), fig2.png (the H6 incident under four evidence conditions) and
fig3.png (confidence floors). Run score_reps.py for both runs first."""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

TIERS = ["haiku", "sonnet", "opus"]
NAME = {"haiku": "Haiku", "sonnet": "Sonnet", "opus": "Opus"}
COL = {"haiku": "#2a78d6", "sonnet": "#eb6834", "opus": "#1baf7a"}
HATCH = {"haiku": "", "sonnet": "///", "opus": "..."}
MARK = {"haiku": "o", "sonnet": "s", "opus": "^"}
INK, MUTED, GRID = "#1f1f1e", "#5f5e5a", "#dddcd6"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.5, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": INK, "ytick.color": INK, "axes.spines.top": False, "axes.spines.right": False,
                     "hatch.linewidth": 0.6})
os.makedirs("results/figures", exist_ok=True)
A = json.load(open("results_api/scored.json"))
C = json.load(open("results_confirm/scored.json"))
SA = json.load(open("results_api/summary.json"))
SC = json.load(open("results_confirm/summary.json"))


# ------------------------------------------------------------------ figure 1
def fig1():
    fig, ax = plt.subplots(figsize=(7.2, 2.5))
    ax.set_xlim(-1, 101.5)
    ax.set_ylim(0, 35)
    ax.axis("off")
    W, H = 22, 14

    def box(col, row, title, lines, fill="#f4f3ef"):
        x, y = col * 26, 20 if row == 0 else 1
        ax.add_patch(FancyBboxPatch((x, y), W, H, boxstyle="round,pad=0.2,rounding_size=1.2", fc=fill, ec=MUTED, lw=0.8))
        ax.text(x + W / 2, y + H - 2.7, title, ha="center", va="center", fontsize=8.3, fontweight="bold", color=INK)
        for i, t in enumerate(lines):
            ax.text(x + W / 2, y + H - 6.6 - 3.1 * i, t, ha="center", va="center", fontsize=6.2, color=INK)

    def arrow(x1, y1, x2, y2, label=None, lx=0, ly=1.4, ha="center"):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=9, lw=0.9, color=MUTED,
                                     shrinkA=0, shrinkB=0))
        if label:
            ax.text((x1 + x2) / 2 + lx, (y1 + y2) / 2 + ly, label, ha=ha, va="center", fontsize=6.6, color=MUTED)

    box(0, 0, "Incident", ["faulty raw tables,", "deployed pipeline SQL,", "change notes"])
    box(1, 0, "Evidence bundle", ["symptom, SQL, column", "profiles, sample rows, notes", "(text only, no queries)"])
    box(2, 0, "Agent", ["decision: fix or escalate,", "confidence from 0 to 1,", "replacement SQL"])
    box(3, 0, "Monitor gate", ["ten data quality checks", "on the repaired tables;", "no ground truth"])
    box(0, 1, "Clean data", ["original pipeline on", "fault-free inputs gives", "the ground truth"], fill="#e8f1f7")
    box(2, 1, "Scorer", ["runs the SQL on the faulty", "data and compares seven", "tables with the ground truth"], fill="#e8f1f7")
    box(3, 1, "Outcome", ["resolved, wrong data,", "unsafe fix, correct or", "unnecessary escalation"])
    arrow(22.6, 27, 25.6, 27)
    arrow(48.6, 27, 51.6, 27)
    arrow(74.6, 27, 77.6, 27)
    arrow(63, 19.6, 63, 15.6, "proposed fix", lx=1.2, ly=0, ha="left")
    arrow(22.6, 8, 51.6, 8, "never shown to the agent")
    arrow(74.6, 8, 77.6, 8)
    arrow(89, 19.6, 89, 15.6, "pass or reject", lx=1.2, ly=0, ha="left")
    fig.savefig("results/figures/fig1.png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ------------------------------------------------------------------ figure 2
def fig2():
    def cnt(rows, cond, seeds, t):
        cs = {f"H6-s{s}" for s in seeds}
        r = [x for x in rows if x["cond"] == cond and x["tier"] == t and x["case"] in cs]
        return sum(x["outcome"] == "unsafe_fix" for x in r), len(r)

    groups = [("Change note\npresent", [(A, "notes", (1, 2)), (C, "notes", (3, 4, 5))]),
              ("No note; conflict\nvisible in samples", [(A, "none", (1,))]),
              ("No note; conflict\nnot in samples", [(A, "none", (2,)), (C, "none", (3, 4, 5))]),
              ("No note; duplicate-key\nprofile added", [(C, "dup_profile", (3, 4, 5))])]
    fig, ax = plt.subplots(figsize=(7.2, 2.7))
    w = 0.25
    for gi, (_, parts) in enumerate(groups):
        for ti, t in enumerate(TIERS):
            k = sum(cnt(r, c, s, t)[0] for r, c, s in parts)
            n = sum(cnt(r, c, s, t)[1] for r, c, s in parts)
            x = gi + (ti - 1) * (w + 0.02)
            ax.bar(x, 100 * k / n, w, color=COL[t], hatch=HATCH[t], edgecolor="white", linewidth=0.8,
                   label=NAME[t] if gi == 0 else None)
            ax.text(x, 100 * k / n + 2.5, f"{k}/{n}", ha="center", va="bottom", fontsize=7.5, color=INK)
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([g for g, _ in groups], fontsize=8)
    ax.set_ylabel("Runs that applied the unsafe fix (%)")
    ax.set_ylim(0, 118)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.yaxis.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", length=0)
    ax.legend(frameon=False, ncol=3, loc="upper left", bbox_to_anchor=(0.0, 1.02), handlelength=1.6, columnspacing=1.4)
    fig.savefig("results/figures/fig2.png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ------------------------------------------------------------------ figure 3
def fig3():
    taus = [0.0, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9]
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 4.1), sharex=True)
    for j, (S, title, nfix) in enumerate(((SA, "Discovery run (seeds 1, 2)", 52), (SC, "Confirmation run (seeds 3 to 5)", 78))):
        for t in TIERS:
            key = lambda tau: f"{t} (gated)|none" if tau == 0 else f"{t}, confidence >= {tau}|none"  # noqa: E731
            harm = [sum(S["policies"][key(tau)]["harmful"]) for tau in taus]
            res = [100 * sum(S["policies"][key(tau)]["resolved"]) / (5 * nfix) for tau in taus]
            x = range(len(taus))
            axes[0][j].plot(x, harm, color=COL[t], marker=MARK[t], ms=4.5, lw=1.6, label=NAME[t], mec="white", mew=0.6)
            axes[1][j].plot(x, res, color=COL[t], marker=MARK[t], ms=4.5, lw=1.6, mec="white", mew=0.6)
            dy = {"haiku": 0, "opus": 9}.get(t, 0)
            axes[1][j].text(len(taus) - 0.75, res[-1] + dy, NAME[t], va="center", fontsize=7.5, color=INK)
        axes[0][j].set_title(title, fontsize=8.5, color=INK, loc="left")
        axes[1][j].set_xticks(range(len(taus)))
        axes[1][j].set_xticklabels(["none"] + [f"{t:.2f}" for t in taus[1:]])
        axes[1][j].set_xlabel("Confidence floor (fixes below it go to a person)")
        axes[1][j].set_xlim(-0.3, len(taus) + 0.45)
        axes[1][j].set_ylim(0, 105)
        for a in (axes[0][j], axes[1][j]):
            a.yaxis.grid(True, color=GRID, lw=0.6)
            a.set_axisbelow(True)
    top = max(axes[0][0].get_ylim()[1], axes[0][1].get_ylim()[1])
    for j in (0, 1):
        axes[0][j].set_ylim(-0.6, top)
    axes[0][0].set_ylabel("Harmful fixes accepted\n(total, five repetitions)")
    axes[1][0].set_ylabel("Fixable incidents\nresolved (%)")
    axes[0][0].legend(frameon=False, loc="upper right", handlelength=2)
    fig.tight_layout(h_pad=1.0, w_pad=1.5)
    fig.savefig("results/figures/fig3.png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


fig1()
fig2()
fig3()
print("wrote results/figures/fig1.png fig2.png fig3.png")
