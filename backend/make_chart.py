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
# Live game AI: peeking + rush-hour cheat  -> frontend/evidence_game.png
# --------------------------------------------------------------------------- #
import json  # noqa: E402
import math  # noqa: E402

game_file = HERE / "results_game.json"
if game_file.exists():
    g = json.loads(game_file.read_text())
    peek, cheat = g["peeking"], g["rush_hour_cheat"]["20pct"]
    hours = peek["hours"]
    p_line = [v * 100 for v in peek["pvalue_every_round"]]
    e_line = [v * 100 for v in peek["evalue_every_round"]]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 9), facecolor=SURFACE,
                                   gridspec_kw={"width_ratios": [2.1, 1], "wspace": 0.22})
    for ax in (ax1, ax2):
        ax.set_facecolor(SURFACE)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.spines["left"].set_color(GRID)
        ax.spines["bottom"].set_color(GRID)
        ax.yaxis.grid(True, color=GRID, linewidth=1)
        ax.set_axisbelow(True)

    # left: chance of ever being fooled vs number of checks
    ax1.plot(hours, p_line, color=NAIVE, linewidth=2.5, label="Ordinary p-value, checked every round")
    ax1.plot(hours, e_line, color=OURS, linewidth=2.5, label="E-values, checked every round (our AI)")
    budget = peek["budget"] * 100
    ax1.axhline(budget, color=INK_2, linewidth=1.2, linestyle=(0, (4, 4)))
    ax1.text(hours[-1], budget + 0.5, f"error budget {budget:.1f}%", ha="right", va="bottom", fontsize=13, color=INK_2)
    ax1.text(hours[-1] + 1, p_line[-1], f"{p_line[-1]:.0f}%", va="center", fontsize=15, color=INK, fontweight="bold")
    ax1.text(hours[-1] + 1, e_line[-1], f"{e_line[-1]:.1f}%", va="center", fontsize=15, color=INK, fontweight="bold")
    ax1.set_xlim(0, hours[-1] + 8)
    top = 5 * math.ceil(max(p_line) * 1.15 / 5)
    ax1.set_ylim(0, top)
    ax1.set_yticks(range(0, top + 1, 5))
    ax1.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax1.set_xlabel("Rounds played (the AI checks after every one)", fontsize=14)
    ax1.set_title("Chance of EVER calling a useless offer real\n(lower is better)",
                  loc="left", fontsize=16, color=INK, pad=14)
    ax1.legend(loc="upper left", frameon=False, fontsize=14)

    # right: the rush-hour cheat in the real game loop
    vals = [cheat["naive_ever_fooled"] * 100, cheat["careful_ever_fooled"] * 100]
    ax2.bar([0, 1], [max(v, 0.6) for v in vals], width=0.6, color=[NAIVE, OURS])
    ax2.set_xticks([0, 1])
    ax2.set_xticklabels(["Naive AI", "Our AI"], fontsize=15, color=INK)
    for x, v in zip([0, 1], vals):
        ax2.text(x, max(v, 0.6) + 2, f"{v:.0f}%" if v >= 10 else f"{v:.1f}%",
                 ha="center", fontsize=16, color=INK, fontweight="bold")
    ax2.set_ylim(0, 112)
    ax2.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax2.set_title("Live game: fooled by a bad offer\nlaunched in rush hours",
                  loc="left", fontsize=16, color=INK, pad=14)
    ax2.text(0.5, -0.17, f"Our AI still confirms the good offer in {cheat['good_confirmed']:.0%} of games\n"
             f"(median {cheat['good_median_round']:.0f} rounds)", transform=ax2.transAxes,
             ha="center", fontsize=13, color=INK_2)

    fig.suptitle(f"Checking after every round fools an ordinary p-value {p_line[-1]:.0f}% of the time. "
                 f"Our e-values: {e_line[-1]:.1f}%.", x=0.035, ha="left", fontsize=20,
                 fontweight="bold", color=INK, y=0.975)
    fig.text(0.035, 0.02, f"Same careful AI, same learned baseline; only the decision rule differs. "
             f"{peek['games']:,} games for the left panel, {g['rush_hour_cheat']['20pct']['games']} for the right, "
             "all fresh games never used for tuning.", fontsize=12, color=INK_2)
    fig.subplots_adjust(left=0.06, right=0.98, top=0.83, bottom=0.17)
    fig.savefig(HERE.parent / "frontend" / "evidence_game.png", dpi=150, facecolor=SURFACE)
    print("saved frontend/evidence_game.png")
