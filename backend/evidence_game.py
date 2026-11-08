"""
Evidence for the LIVE game AI (backend/agents.py), played through the real game loop (game.py).

  python -m backend.evidence_game          (from the repo root, ~1 min)
      -> backend/results_game.json, then: python -m backend.make_chart

Each game: 6 months of past sales, then 16 offers, each running two shop days, judged blind
(the AI is never told good or bad). Every offer gets a forced verdict, REAL or not.
Three ways of deciding are scored on the SAME offers:
  naive       plain average vs an average hour (> +20% = REAL)
  gut         the careful AI's habit-based probability > 50% (learns the player's habits)
  ours        the careful AI's actual rule: evidence (e-value) >= 20
Three player strategies:
  random      good or bad at random, launched at random times
  cheater     bad offers launched before weekends, with an event and friends called in;
              good offers on quiet weekdays
  switcher    teaches the AI a habit for 8 offers (bad = weekend), then flips it
Seeds 130000+ are fresh: the two-day offer length was chosen on other games.
"""
import json
import random
from pathlib import Path

from .game import OFFER_LOCK_HOURS, Game

HERE = Path(__file__).parent
SEED = 130000
STRATEGIES = ("random", "cheater", "switcher")
METHODS = ("naive", "gut", "ours")


def _run_offer(game: Game, kind: str, cheat: bool = False) -> dict:
    while game.popups:
        game.dismiss_popup()
    started = game.launch_offer(kind)
    assert started["ok"], started["error"]
    if cheat and kind == "bad":
        game.trigger_event("random")
        game.call_friends()
    for _ in range(OFFER_LOCK_HOURS * 3):
        while game.popups:
            pop = game.popups[0]
            game.dismiss_popup()
            if pop["type"] == "verdict":
                return pop
        game.tick()
    raise RuntimeError("no verdict")


def _wait(game: Game, cond, max_hours: int) -> None:
    for _ in range(max_hours):
        while game.popups:
            game.dismiss_popup()
        if cond(game):
            return
        game.tick()


def play(seed: int, effect: float, strategy: str, offers: int = 16) -> list:
    game, rng = Game(seed=seed, good_effect=effect), random.Random(seed)
    rows = []
    for i in range(offers):
        kind = rng.choice(["good", "bad"])
        if strategy == "random":
            _wait(game, lambda g: False, rng.randint(0, 6))
            pop = _run_offer(game, kind)
        elif strategy == "cheater":
            if kind == "bad":
                _wait(game, lambda g: g.shop.weekday_idx >= 4 and g.shop.hour == 9, 7 * 12)
            else:
                _wait(game, lambda g: g.shop.weekday_idx <= 2 and g.shop.hour == 9, 7 * 12)
            pop = _run_offer(game, kind, cheat=True)
        else:  # switcher
            weekend = (kind == "bad") == (i < offers // 2)
            if weekend:
                _wait(game, lambda g: g.shop.weekday_idx >= 5 and g.shop.hour == 9, 7 * 12)
            else:
                _wait(game, lambda g: g.shop.weekday_idx <= 3 and g.shop.hour == 9, 7 * 12)
            pop = _run_offer(game, kind)
        c = pop["careful"]
        rows.append({"offer": i, "kind": kind,
                     "naive": pop["naive"]["verdict"] == "REAL",
                     "gut": c["probability"] > 0.5,
                     "ours": c["verdict"] == "REAL"})
    return rows


def evaluate(games: int = 40, offers: int = 16, effects=(0.20, 0.08), seed: int = SEED) -> dict:
    out = {"games": games, "offers_per_game": offers, "offer_hours": OFFER_LOCK_HOURS, "results": {}}
    for effect in effects:
        key = f"{int(round(effect * 100))}pct"
        out["results"][key] = {}
        for strategy in STRATEGIES:
            rows = [r for g in range(games) for r in play(seed + g, effect, strategy, offers)]
            bad = [r for r in rows if r["kind"] == "bad"]
            good = [r for r in rows if r["kind"] == "good"]
            out["results"][key][strategy] = {
                m: {"fooled": sum(r[m] for r in bad) / len(bad),
                    "found": sum(r[m] for r in good) / len(good)} for m in METHODS}
            out["results"][key][strategy]["n_bad"], out["results"][key][strategy]["n_good"] = len(bad), len(good)
            if strategy == "switcher":
                late = [r for r in bad if r["offer"] >= offers // 2]
                out["results"][key][strategy]["after_switch_fooled"] = {
                    m: sum(r[m] for r in late) / len(late) for m in METHODS}
    return out


if __name__ == "__main__":
    res = evaluate()
    for key, by_strategy in res["results"].items():
        print(f"good offer +{key[:-3]}%:")
        for strategy, r in by_strategy.items():
            cells = "  ".join(f"{m}: fooled {r[m]['fooled']:5.1%} found {r[m]['found']:5.1%}" for m in METHODS)
            print(f"  {strategy:9s} {cells}")
    out = HERE / "results_game.json"
    out.write_text(json.dumps(res, indent=1))
    print(f"saved {out}")
