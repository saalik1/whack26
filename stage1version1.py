"""
Stage 1 prototype: can an AI researcher tell a real discovery from a lucky one?

A simulated shop runs 90 days. Each day a set of "tweaks" (discount, banner colour,
music, ...) are switched on or off at random. Only the ones in TRUE_EFFECTS really
change revenue; the rest are the attacker's "fish for luck" cheat: lots of
meaningless tweaks hoping one looks good by chance.

Two researchers look at the same data:
  - Naive:   t-test every tweak on all 90 days, declare anything with p < 0.05.
  - Popper:  explore on days 1-60, pre-register the suspects, then try to falsify
             them on the unseen days 61-90 with a permutation test + Benjamini-Hochberg.

Run:  python stage1.py
"""
import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

N_DAYS = 90
EXPLORE_DAYS = 60
BASELINE = 1000.0          # average daily revenue (GBP)
NOISE_SD = 60.0            # day-to-day randomness
WEEKLY = [0, -40, -30, -20, 10, 90, 70]   # Mon..Sun pattern
TRUE_EFFECTS = {"discount_10pct": 80.0}  # the only real effect (+8%)
N_FAKE_TWEAKS = 20         # attacker's meaningless tweaks
ALPHA = 0.05


# ---------------------------------------------------------------- simulator
def simulate(seed=None, pure_noise=False, n_fake=N_FAKE_TWEAKS):
    """Return (DataFrame of daily sales + tweak switches, dict of true effects)."""
    rng = np.random.default_rng(seed)
    truth = {} if pure_noise else dict(TRUE_EFFECTS)
    names = list(truth) + [f"tweak_{i:02d}" for i in range(n_fake)]
    df = pd.DataFrame({"day": np.arange(N_DAYS)})
    df["weekday"] = df["day"] % 7
    revenue = BASELINE + np.array(WEEKLY)[df["weekday"]] + rng.normal(0, NOISE_SD, N_DAYS)
    for name in names:
        df[name] = rng.integers(0, 2, N_DAYS)          # on/off at random each day
        revenue += df[name] * truth.get(name, 0.0)
    df["revenue"] = revenue
    return df, truth


def tweak_columns(df):
    return [c for c in df.columns if c not in ("day", "weekday", "revenue")]


# ---------------------------------------------------------------- researchers
def naive_researcher(df):
    """Plain t-test on all the data, no correction. Easily fooled."""
    found = []
    for t in tweak_columns(df):
        on, off = df.loc[df[t] == 1, "revenue"], df.loc[df[t] == 0, "revenue"]
        if stats.ttest_ind(on, off).pvalue < ALPHA:
            found.append(t)
    return found


def _diff_in_means(x, y, axis=-1):
    return np.mean(x, axis=axis) - np.mean(y, axis=axis)


def _perm_pvalue(df, tweak, rng):
    # remove the known weekly pattern first so it can't masquerade as an effect
    resid = df["revenue"] - df.groupby("weekday")["revenue"].transform("mean")
    on, off = resid[df[tweak] == 1].to_numpy(), resid[df[tweak] == 0].to_numpy()
    if len(on) < 3 or len(off) < 3:
        return 1.0
    res = stats.permutation_test((on, off), _diff_in_means, vectorized=True,
                                 n_resamples=999, alternative="two-sided", random_state=rng)
    return res.pvalue


def popper_researcher(df, seed=0, verbose=False):
    """Conjecture on old data, pre-register, then try to falsify on unseen data."""
    rng = np.random.default_rng(seed)
    explore, holdout = df[df["day"] < EXPLORE_DAYS], df[df["day"] >= EXPLORE_DAYS]

    # 1. Conjecture: anything that looks promising in the exploration data
    suspects = [t for t in tweak_columns(df) if _perm_pvalue(explore, t, rng) < ALPHA]
    if verbose:
        print(f"  Pre-registered suspects (before seeing days {EXPLORE_DAYS + 1}-{N_DAYS}): {suspects or 'none'}")
    if not suspects:
        return []

    # 2. Attack: re-test only the suspects on unseen data, correct for how many we test
    pvals = [_perm_pvalue(holdout, t, rng) for t in suspects]
    survived, adj, _, _ = multipletests(pvals, alpha=ALPHA, method="fdr_bh")
    if verbose:
        for t, p, ok in zip(suspects, adj, survived):
            print(f"    {t:16s} holdout p (BH-adjusted) = {p:.3f}  -> {'SURVIVED' if ok else 'FALSIFIED'}")
    return [t for t, ok in zip(suspects, survived) if ok]


# ---------------------------------------------------------------- scoring
def score(found, truth):
    real = [f for f in found if f in truth]
    fake = [f for f in found if f not in truth]
    return real, fake


def run_demo(seed=7):
    print("=" * 64)
    print("ONE GAME: 1 real effect hidden among 20 meaningless tweaks")
    print("=" * 64)
    df, truth = simulate(seed)
    naive = naive_researcher(df)
    r, f = score(naive, truth)
    print(f"Naive researcher declares: {naive}")
    print(f"  -> real found: {r}   fake 'discoveries': {f}\n")
    print("Popper researcher:")
    ours = popper_researcher(df, seed, verbose=True)
    r, f = score(ours, truth)
    print(f"  -> declares: {ours}")
    print(f"  -> real found: {r}   fake 'discoveries': {f}")


def run_noise_check(seed=11):
    print("\n" + "=" * 64)
    print("PURE NOISE CHECK: nothing is real, the right answer is 'nothing'")
    print("=" * 64)
    df, truth = simulate(seed, pure_noise=True)
    print(f"Naive researcher declares:  {naive_researcher(df)}")
    print(f"Popper researcher declares: {popper_researcher(df, seed)}")


def run_benchmark(n_games=200):
    print("\n" + "=" * 64)
    print(f"BENCHMARK: {n_games} games")
    print("=" * 64)
    rows = []
    for g in range(n_games):
        df, truth = simulate(seed=1000 + g)
        for name, found in (("naive", naive_researcher(df)), ("popper", popper_researcher(df, g))):
            real, fake = score(found, truth)
            rows.append({"agent": name, "found_real": len(real) > 0,
                         "n_fake": len(fake), "any_fake": len(fake) > 0})
    res = pd.DataFrame(rows).groupby("agent").agg(
        real_effect_found=("found_real", "mean"),
        games_with_a_fake_discovery=("any_fake", "mean"),
        fake_discoveries_per_game=("n_fake", "mean"))
    print(res.round(3).to_string())
    return res


if __name__ == "__main__":
    run_demo()
    run_noise_check()
    run_benchmark()