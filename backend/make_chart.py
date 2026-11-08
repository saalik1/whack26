"""
Make the evidence slide chart from results.csv.

  python -m backend.make_chart     (from the repo root) -> frontend/evidence.png

Left panel:  how often each AI was fooled by the cheat (lower is better).
Right panel: how often our AI still finds the real effect (higher is better).
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker  # noqa: F401
import pandas as pd
from pathlib import Path

HERE = Path(__file__).parent

SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
OURS, NAIVE = "#2a78d6", "#eb6834"          # categorical slot 1 (blue), slot 2 (orange)

LABELS = {"none": "Fishing for luck\n(20 useless tweaks)", "confounder": "Two changes at once",
          "seasonality": "Riding a sales trend", "promo_timing": "Promos on busy days",
          "fake_customers": "Fake customers", "peeking": "Stopping early"}

res = pd.read_csv(HERE / "results.csv").set_index("cheat")
n_games = 200 * len(res)
order = ["promo_timing", "fake_customers", "confounder", "none", "seasonality", "peeking"]
res = res.loc[order]
names = [LABELS[c] for c in order]
y = range(len(order))[::-1]

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 15, "text.color": INK,
                     "axes.labelcolor": INK_2, "xtick.color": INK_2, "ytick.color": INK})
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 9), facecolor=SURFACE,
                               gridspec_kw={"width_ratios": [2.1, 1], "wspace": 0.08})
h = 0.36
for ax in (ax1, ax2):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.xaxis.grid(True, color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)
    ax.set_xlim(0, 108)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"])

# left: fooled by the cheat
naive = res["naive_fooled"] * 100
ours = res["popper_fooled"] * 100
ax1.barh([v + h / 2 for v in y], naive, height=h - 0.03, color=NAIVE, label="Naive AI (plain p-value)")
ax1.barh([v - h / 2 for v in y], ours.clip(lower=0.6), height=h - 0.03, color=OURS, label="Our AI")
for v, a, b in zip(y, naive, ours):
    ax1.text(a + 1.2, v + h / 2, f"{a:.0f}%", va="center", fontsize=14, color=INK_2)
    ax1.text(max(b, 0.6) + 1.2, v - h / 2, ("0%" if b == 0 else f"{b:.1f}%") if b < 10 else f"{b:.0f}%",
             va="center", fontsize=14, color=INK, fontweight="bold")
ax1.set_yticks(list(y))
ax1.set_yticklabels(names, fontsize=15)
ax1.set_title("How often the AI was fooled by the cheat\n(lower is better)",
              loc="left", fontsize=16, color=INK, pad=14)
ax1.legend(loc="lower right", frameon=False, fontsize=14)

# right: still finds the real effect
found = res["popper_discount_found"] * 100
ax2.barh(list(y), found, height=h * 1.4, color=OURS)
for v, f in zip(y, found):
    ax2.text(f - 1.5, v, f"{f:.0f}%", va="center", ha="right", fontsize=14, color="white", fontweight="bold")
ax2.set_yticks([])
ax2.set_title("Our AI still finds the real effect\n(higher is better)", loc="left", fontsize=16, color=INK, pad=14)

fig.suptitle("Naive AI fooled up to 100% of the time. Ours: under 8%, while still finding the real effect.",
             x=0.035, ha="left", fontsize=21, fontweight="bold", color=INK, y=0.975)
fig.text(0.035, 0.02, f"{n_games:,} simulated shop games ({len(res)} cheats x 200), all fresh games never used "
         "for tuning. 'Fooled' = declared the cheat's useless promo real.",
         fontsize=12, color=INK_2)
fig.subplots_adjust(left=0.17, right=0.98, top=0.84, bottom=0.1)
fig.savefig(HERE.parent / "frontend" / "evidence.png", dpi=150, facecolor=SURFACE)
print("saved frontend/evidence.png")


# --------------------------------------------------------------------------- #
# Live game AI: three ways of deciding, three player strategies -> frontend/evidence_game.png
# --------------------------------------------------------------------------- #
import json  # noqa: E402

GUT = "#1baf7a"                                   # categorical slot 3 (aqua)
game_file = HERE / "results_game.json"
if game_file.exists():
    g = json.loads(game_file.read_text())
    res = g["results"]["20pct"]
    strategies = ["random", "cheater", "switcher"]
    names = {"random": "Random player", "cheater": "Cheater\n(busy days, events,\nfriends)",
             "switcher": "Switcher\n(teaches a habit,\nthen flips it)"}
    methods = [("naive", "Naive AI (plain average)", NAIVE),
               ("gut", "Gut feeling (learns your habits)", GUT),
               ("ours", "Our AI (evidence only, e-value)", OURS)]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 9), facecolor=SURFACE,
                                   gridspec_kw={"wspace": 0.12})
    w = 0.26
    for ax, metric, title in ((ax1, "fooled", "Useless offer called REAL  (lower is better)"),
                              (ax2, "found", "Good (+20%) offer called REAL  (higher is better)")):
        ax.set_facecolor(SURFACE)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.spines["left"].set_color(GRID)
        ax.spines["bottom"].set_color(GRID)
        ax.yaxis.grid(True, color=GRID, linewidth=1)
        ax.set_axisbelow(True)
        for j, (m, label, colour) in enumerate(methods):
            xs = [k + (j - 1) * w for k in range(len(strategies))]
            vals = [res[s_][m][metric] * 100 for s_ in strategies]
            ax.bar(xs, [max(v, 0.7) for v in vals], width=w - 0.03, color=colour, label=label)
            for x, v in zip(xs, vals):
                ax.text(x, max(v, 0.7) + 1.5, f"{v:.0f}%" if v >= 10 else f"{v:.1f}%",
                        ha="center", fontsize=12, color=INK, fontweight="bold" if m == "ours" else "normal")
        ax.set_xticks(range(len(strategies)))
        ax.set_xticklabels([names[s_] for s_ in strategies], fontsize=13, color=INK)
        ax.set_ylim(0, 110)
        ax.set_yticks(range(0, 101, 25))
        ax.set_yticklabels([f"{v}%" for v in range(0, 101, 25)])
        ax.set_title(title, loc="left", fontsize=16, color=INK, pad=12)
    ax1.legend(loc="upper left", frameon=False, fontsize=13)

    worst_ours = max(res[s_]["ours"]["fooled"] for s_ in strategies) * 100
    worst_naive = max(res[s_]["naive"]["fooled"] for s_ in strategies) * 100
    fig.suptitle(f"In the live game the naive AI is fooled up to {worst_naive:.0f}% of the time. "
                 f"Ours: at most {worst_ours:.1f}%.", x=0.035, ha="left", fontsize=20,
                 fontweight="bold", color=INK, y=0.975)
    fig.text(0.035, 0.02, f"{g['games']} games x {g['offers_per_game']} offers per strategy, each offer runs "
             f"{g['offer_hours']} shop hours and is judged blind. Fresh games, never used to tune anything.",
             fontsize=12, color=INK_2)
    fig.subplots_adjust(left=0.05, right=0.99, top=0.86, bottom=0.2)
    fig.savefig(HERE.parent / "frontend" / "evidence_game.png", dpi=150, facecolor=SURFACE)
    print("saved frontend/evidence_game.png")
