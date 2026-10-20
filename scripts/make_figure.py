"""Figure 1: incidents resolved against harmful fixes as the confidence threshold rises."""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

S = json.load(open("results/sweep.json"))
col = {"haiku": "#2a78d6", "sonnet": "#eb6834", "opus": "#1baf7a", "cascade": "#eda100"}
mk = {"haiku": "o", "sonnet": "s", "opus": "^", "cascade": "D"}
nm = {"haiku": "Haiku", "sonnet": "Sonnet", "opus": "Opus", "cascade": "Haiku>Sonnet>Opus cascade"}
off = {"haiku": 0, "sonnet": 0.06, "opus": -0.06, "cascade": 0}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9})
fig, axs = plt.subplots(1, 2, figsize=(7.2, 3.2), sharey=True)
for ax, (cond, title) in zip(axs, (("notes", "(a) With change notes"), ("none", "(b) Change notes removed"))):
    for p in ("haiku", "sonnet", "opus", "cascade"):
        rs = [r for r in S[cond] if r["policy"] == p and r["tau"] in (0.0, 0.65, 0.75, 0.85)]
        ax.plot([r["resolved"] for r in rs], [r["harmful"] + off[p] for r in rs], color=col[p], lw=2,
                marker=mk[p], ms=6, markeredgecolor="white", markeredgewidth=1, label=nm[p], zorder=3)
    ax.set_title(title, fontsize=9, loc="left")
    ax.set_xlabel("Incidents resolved (of 52 fixable)")
    ax.grid(color="#e6e5e0", lw=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_xlim(10, 54)
    ax.set_yticks([0, 1, 2, 3])
axs[0].set_ylabel("Harmful fixes accepted")
h, l = axs[0].get_legend_handles_labels()
fig.legend(h, l, frameon=False, fontsize=8, ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.06))
fig.text(0.5, -0.03, "Each line runs right to left over confidence thresholds 0, 0.65, 0.75 and 0.85. "
         "Small vertical offsets separate overlapping lines.", ha="center", fontsize=7.5, color="#555")
fig.tight_layout()
fig.savefig("results/fig_tradeoff.png", dpi=300, bbox_inches="tight")
print("wrote results/fig_tradeoff.png")
