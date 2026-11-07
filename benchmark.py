"""
Demo, sanity checks and benchmark.

  python benchmark.py                          demo + pure-noise check + benchmark (no cheat)
  python benchmark.py --cheat fake_customers   same, with one cheat
  python benchmark.py --cheat all --games 100  table of every cheat, saved to results.csv
  python benchmark.py --tune                   tune the "split" design (explore split / threshold)
"""
import argparse

import numpy as np
import pandas as pd

from defender import naive_researcher, popper_researcher
from simulator import CHEATS, CHEAT_TARGET, simulate


def score(result, truth, cheat):
    real_found = [t for t, v in result.items() if v["verdict"] == "real" and truth.get(t, 0) != 0]
    fakes = [t for t, v in result.items() if v["verdict"] == "real" and truth.get(t, 0) == 0]
    target = CHEAT_TARGET.get(cheat)
    return {
        "fooled_by_cheat": (target in fakes) if target else len(fakes) > 0,
        "any_fake": len(fakes) > 0,
        "discount_found": result.get("discount_10pct", {}).get("verdict") == "real",
        "any_not_sure": any(v["verdict"] == "not_sure" for v in result.values()),
        "real_found": real_found, "fakes": fakes,
    }


def demo(cheat, seed=3):
    print("=" * 70)
    print(f"ONE GAME  (cheat: {cheat})")
    print("=" * 70)
    df, truth = simulate(seed, cheat=cheat)
    if df.attrs.get("stopped_early"):
        print(f"  attacker stopped the experiment early, on day {len(df)}")
    naive = score(naive_researcher(df), truth, cheat)
    print(f"Naive declares real: {naive['real_found'] + naive['fakes']}  -> fake discoveries: {naive['fakes']}")
    print("Popper:")
    res = popper_researcher(df, seed, verbose=True)
    s = score(res, truth, cheat)
    unsure = [t for t, v in res.items() if v["verdict"] == "not_sure"]
    print(f"  declares real: {s['real_found'] + s['fakes']}   not sure: {unsure or 'none'}"
          f"   fake discoveries: {s['fakes'] or 'none'}")


def noise_check(seed=11):
    print("\n" + "=" * 70)
    print("PURE NOISE CHECK (nothing is real; the right answer is 'nothing')")
    print("=" * 70)
    df, truth = simulate(seed, pure_noise=True)
    n = [t for t, v in naive_researcher(df).items() if v["verdict"] == "real"]
    p = [t for t, v in popper_researcher(df, seed).items() if v["verdict"] == "real"]
    print(f"Naive declares:  {n}\nPopper declares: {p}")


# Tuning and evaluation use different games, so reported numbers are never
# measured on the games the settings were chosen on.
TUNE_SEED = 1000
EVAL_SEED = 50000


def wilson(k, n, z=1.96):
    """95% confidence interval for a rate of k successes out of n."""
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def run_cheat(cheat, games, seed_base=EVAL_SEED, **kw):
    rows = []
    for g in range(games):
        df, truth = simulate(seed=seed_base + g, cheat=cheat)
        for name, res in (("naive", naive_researcher(df)), ("popper", popper_researcher(df, g, **kw))):
            s = score(res, truth, cheat)
            rows.append({"agent": name, **{k: s[k] for k in
                         ("fooled_by_cheat", "any_fake", "discount_found", "any_not_sure")}})
    return pd.DataFrame(rows).groupby("agent").mean()


def benchmark(cheat, games):
    print("\n" + "=" * 70)
    print(f"BENCHMARK  {games} fresh games, never used for tuning  (cheat: {cheat})")
    print("=" * 70)
    print(run_cheat(cheat, games).round(3).to_string())


def benchmark_all(games):
    rows = []
    for cheat in CHEATS:
        t = run_cheat(cheat, games)
        lo, hi = wilson(round(t.loc["popper", "fooled_by_cheat"] * games), games)
        rows.append({"cheat": cheat,
                     "naive_fooled": t.loc["naive", "fooled_by_cheat"],
                     "popper_fooled": t.loc["popper", "fooled_by_cheat"],
                     "popper_fooled_95ci": f"{lo:.3f}-{hi:.3f}",
                     "popper_any_fake": t.loc["popper", "any_fake"],
                     "popper_discount_found": t.loc["popper", "discount_found"],
                     "popper_not_sure": t.loc["popper", "any_not_sure"]})
        print(f"  done: {cheat}", flush=True)
    res = pd.DataFrame(rows).set_index("cheat").round(3)
    print("\n" + res.to_string())
    res.to_csv("results.csv")
    print(f"\n{games} fresh games per cheat (seeds {EVAL_SEED}+), never used for tuning. Saved results.csv")


def tune(games):
    print("explore_frac  explore_alpha  discount_found  any_fake")
    for frac in (0.5, 0.67):
        for alpha in (0.05, 0.10, 0.20):
            t = run_cheat("none", games, seed_base=TUNE_SEED, design="split",
                          explore_frac=frac, explore_alpha=alpha).loc["popper"]
            print(f"{frac:12.2f}  {alpha:13.2f}  {t['discount_found']:14.3f}  {t['any_fake']:8.3f}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cheat", default="none")
    ap.add_argument("--games", type=int, default=200)
    ap.add_argument("--tune", action="store_true")
    a = ap.parse_args()
    if a.tune:
        tune(a.games)
    elif a.cheat == "all":
        benchmark_all(a.games)
    else:
        demo(a.cheat)
        noise_check()
        benchmark(a.cheat, a.games)
