"""
Evidence for the LIVE game AI (backend/agents.py).

  python -m backend.evidence_game          (from the repo root, ~1 min)
      -> backend/results_game.json, then run: python -m backend.make_chart

1. Peeking. A useless offer runs every hour and the AI checks after EVERY hour, the way
   the game works. We compare the same careful AI (same learned baseline, same allowance
   for its own uncertainty) deciding with:
     - an ordinary p-value, checked every hour      (the "stop when it looks good" trap)
     - an ordinary p-value, checked once at the end (fine, but useless in a live game)
     - e-values, checked every hour                  (what our AI actually uses)
   and measure how often each has EVER called the useless offer REAL.

2. The rush-hour cheat in the real game loop (Game.play): bad offer only in rush hours,
   good offer otherwise. How often is each AI fooled, and how fast does ours confirm the
   good offer?

All games use fresh seeds (70000+, 80000+) that were never used to choose any setting.
"""
import json
import math
import statistics
from pathlib import Path

from .agents import ALPHA, E_THRESHOLD, OFFERS, CarefulAgent
from .game import PAST_HOURS, Game
from .simulator2 import RUSH_THRESHOLD, Shop

HERE = Path(__file__).parent
PEEK_SEED, CHEAT_SEED = 70000, 80000
P_LEVEL = ALPHA / len(OFFERS)          # same 2.5% per-offer budget the e-value uses


def _norm_sf(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2))


def peeking(games: int = 1000, hours: int = 100) -> dict:
    ever_p = [0] * hours        # ever fooled by round r, ordinary p-value checked every round
    ever_e = [0] * hours        # ever fooled by round r, e-value checked every round
    once_p = [0] * hours        # p-value checked ONCE, at round r
    for g in range(games):
        shop = Shop(seed=PEEK_SEED + g)
        shop.run(PAST_HOURS)
        agent = CarefulAgent(shop.history)
        fooled_p = fooled_e = False
        for r in range(hours):
            agent.judge(shop.step("bad"))
            ev = agent.evidence["bad"]
            p = _norm_sf(ev.S_eff / math.sqrt(ev.tries))
            fooled_p |= p <= P_LEVEL
            fooled_e |= ev.e >= E_THRESHOLD
            ever_p[r] += fooled_p
            ever_e[r] += fooled_e
            once_p[r] += p <= P_LEVEL
    return {"games": games, "hours": list(range(1, hours + 1)),
            "pvalue_every_round": [x / games for x in ever_p],
            "evalue_every_round": [x / games for x in ever_e],
            "pvalue_once_at_end": [x / games for x in once_p],
            "budget": P_LEVEL}


def rush_hour_cheat(games: int = 300, rounds: int = 60, good_effect: float = 0.20) -> dict:
    careful_fooled = naive_fooled = 0
    good_found_at = []
    for g in range(games):
        game = Game(seed=CHEAT_SEED + g, good_effect=good_effect)
        c_fooled = n_fooled = False
        found = None
        for r in range(1, rounds + 1):
            rush = game.shop.forecast_next_hour()["expected"] >= RUSH_THRESHOLD
            offer = "bad" if rush else "good"
            out = game.play(offer)
            if offer == "bad":
                c_fooled |= out["careful"]["verdict"] == "REAL"
                n_fooled |= out["naive"]["verdict"] == "REAL"
            elif found is None and out["careful"]["verdict"] == "REAL":
                found = r
        careful_fooled += c_fooled
        naive_fooled += n_fooled
        if found:
            good_found_at.append(found)
    return {"games": games, "rounds": rounds, "good_effect": good_effect,
            "naive_ever_fooled": naive_fooled / games,
            "careful_ever_fooled": careful_fooled / games,
            "good_confirmed": len(good_found_at) / games,
            "good_median_round": statistics.median(good_found_at) if good_found_at else None}


if __name__ == "__main__" and "--forced" not in __import__("sys").argv:
    print("peeking experiment (1,000 games x 100 hours)...", flush=True)
    peek = peeking()
    for h in (10, 25, 50, 100):
        i = h - 1
        print(f"  after {h:3d} checks: p-value every round fooled {peek['pvalue_every_round'][i]:.1%} | "
              f"e-value every round {peek['evalue_every_round'][i]:.1%} | "
              f"p-value once {peek['pvalue_once_at_end'][i]:.1%}", flush=True)
    print("rush-hour cheat in the real game loop...", flush=True)
    cheat = {f"{int(e * 100)}pct": rush_hour_cheat(good_effect=e) for e in (0.20, 0.08)}
    for k, v in cheat.items():
        print(f"  good offer +{k}: naive fooled {v['naive_ever_fooled']:.0%}, ours {v['careful_ever_fooled']:.1%}; "
              f"good offer confirmed in {v['good_confirmed']:.0%} of games (median round {v['good_median_round']})")
    out = HERE / "results_game.json"
    out.write_text(json.dumps({"peeking": peek, "rush_hour_cheat": cheat}, indent=1))
    print(f"saved {out}")


# --------------------------------------------------------------------------- #
# 3. Forced decision: no hiding behind NOT SURE
# --------------------------------------------------------------------------- #
def forced_decision(games: int = 300, hours: int = 120, good_effect: float = 0.20, seed: int = 95000) -> dict:
    """Run the rush-hour cheat for `hours` trading hours (10 days), then EVERY method must
    answer: REAL, or "not proven -> treat as no effect". NOT SURE counts as "no".
    Scored on both mistakes: bad offer called REAL (fooled), good offer not called REAL (missed)."""
    from scipy import stats
    methods = ["ab_test_once", "pvalue_every_hour", "pvalue_once", "evalue_every_hour"]
    called_real = {m: {"good": 0, "bad": 0} for m in methods}
    for g in range(games):
        shop = Shop(seed=seed + g, good_effect=good_effect)
        shop.run(PAST_HOURS)
        normal_hours = [r.customers for r in shop.history]          # 8 weeks, no offers
        agent = CarefulAgent(shop.history)
        seen = {"good": [], "bad": []}
        peeked = {"good": False, "bad": False}
        e_hit = {"good": False, "bad": False}
        for _ in range(hours):
            offer = "bad" if shop.forecast_next_hour()["expected"] >= RUSH_THRESHOLD else "good"
            rec = shop.step(offer)
            agent.judge(rec)
            seen[offer].append(rec.customers)
            ev = agent.evidence[offer]
            peeked[offer] |= _norm_sf(ev.S_eff / math.sqrt(ev.tries)) <= P_LEVEL
            e_hit[offer] |= ev.e >= E_THRESHOLD
        for offer in OFFERS:
            ev = agent.evidence[offer]
            if len(seen[offer]) >= 2:
                ab_p = stats.ttest_ind(seen[offer], normal_hours, alternative="greater").pvalue
                called_real["ab_test_once"][offer] += ab_p <= P_LEVEL
            if ev.tries:
                called_real["pvalue_once"][offer] += _norm_sf(ev.S_eff / math.sqrt(ev.tries)) <= P_LEVEL
            called_real["pvalue_every_hour"][offer] += peeked[offer]
            called_real["evalue_every_hour"][offer] += e_hit[offer]
    return {"games": games, "hours": hours, "good_effect": good_effect,
            "fooled": {m: called_real[m]["bad"] / games for m in methods},
            "found": {m: called_real[m]["good"] / games for m in methods}}


if __name__ == "__main__" and "--forced" in __import__("sys").argv:
    out = HERE / "results_game.json"
    data = json.loads(out.read_text())
    data["forced_decision"] = {f"{int(e * 100)}pct": forced_decision(good_effect=e) for e in (0.20, 0.08)}
    out.write_text(json.dumps(data, indent=1))
    for k, v in data["forced_decision"].items():
        print(f"good offer +{k} after {v['hours']} hours, {v['games']} games:")
        for m in v["fooled"]:
            print(f"  {m:20s} fooled (bad called REAL) {v['fooled'][m]:6.1%}   found (good called REAL) {v['found'][m]:6.1%}")
    print(f"saved {out}")
