"""
The two AI researchers.

Both return {tweak: {"verdict": "real" | "fake" | "not_sure", "p": float, "reason": str}}

Naive:  plain t-test on all the data, "real" if p < 0.05. No defences.

Popper: tries to prove every idea wrong before believing it. All defences are
general rules, none of them knows which cheat is being played.
  1. Separability  - tweaks that always change together can't be told apart -> not_sure
  2. Trend removal - strip slow trends (STL) so a rising market can't pose as an effect
  3. Calendar      - control for weekday and payday so busy days can't pose as an effect
  4. Pre-register  - hypotheses are fixed before looking at results
  5. Falsify       - one severe permutation test per hypothesis, Holm correction
                     (design="split" instead conjectures on early days, re-tests on unseen days)
  6. Outliers      - judge on typical-sized orders, so a few unusual buyers can't fake an effect
"""
import numpy as np
from scipy import stats
from statsmodels.stats.multitest import multipletests
from statsmodels.tsa.seasonal import STL

from simulator import tweak_columns

ALPHA = 0.05
EXPLORE_FRAC = 0.5       # tuned with benchmark.py --tune
EXPLORE_ALPHA = 0.05     # tuned with benchmark.py --tune
CORR_LIMIT = 0.95
N_PERM = 999
N_PERM_FINE = 19999


# ------------------------------------------------------------------ naive
def naive_researcher(df):
    out = {}
    for t in tweak_columns(df):
        on, off = df.loc[df[t] == 1, "revenue"], df.loc[df[t] == 0, "revenue"]
        p = stats.ttest_ind(on, off).pvalue if min(len(on), len(off)) > 1 else 1.0
        out[t] = {"verdict": "real" if p < ALPHA else "fake", "p": float(p),
                  "reason": "t-test on all days" + (" says it works" if p < ALPHA else " finds nothing")}
    return out


# ------------------------------------------------------------------ helpers
def _detrend(y):
    """Remove the slow trend with STL (period 7), keep the day-to-day signal."""
    if len(y) < 21:
        return y - y.mean()
    trend = STL(y, period=7, robust=True).fit().trend
    return y - trend


def _calendar_residuals(y, part):
    """Residuals after regressing on weekday dummies + payday (fitted on this part only)."""
    X = np.column_stack([np.ones(len(part))]
                        + [(part["weekday"] == k).to_numpy(float) for k in range(1, 7)]
                        + [part["is_payday"].to_numpy(float)])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return y - X @ beta


def _diff(x, y, axis=-1):
    return np.mean(x, axis=axis) - np.mean(y, axis=axis)


def _perm_p(resid, flag, rng):
    """Permutation p-value. Small p-values are refined with more shuffles, because
    999 shuffles can't resolve p-values below ~0.002 (a strict multiple-testing
    cut-off needs finer resolution than that)."""
    on, off = resid[flag == 1], resid[flag == 0]
    if len(on) < 3 or len(off) < 3:
        return 1.0
    p = stats.permutation_test((on, off), _diff, vectorized=True, n_resamples=N_PERM,
                               alternative="two-sided", random_state=rng).pvalue
    if p <= 0.02:
        p = stats.permutation_test((on, off), _diff, vectorized=True, n_resamples=N_PERM_FINE,
                                   alternative="two-sided", random_state=rng).pvalue
    return float(p)


def _inseparable_groups(df, tweaks):
    """Tweaks that are (almost) always switched on/off together."""
    groups, seen = [], set()
    X = df[tweaks].to_numpy(float)
    std = X.std(axis=0)
    for i, a in enumerate(tweaks):
        if a in seen or std[i] == 0:
            continue
        group = [a]
        for j in range(i + 1, len(tweaks)):
            b = tweaks[j]
            if b not in seen and std[j] > 0 and abs(np.corrcoef(X[:, i], X[:, j])[0, 1]) > CORR_LIMIT:
                group.append(b)
        if len(group) > 1:
            groups.append(group)
            seen.update(group)
    return groups


# ------------------------------------------------------------------ Popper
def popper_researcher(df, seed=0, design="preregistered", explore_frac=EXPLORE_FRAC,
                      explore_alpha=EXPLORE_ALPHA, verbose=False):
    """
    design="preregistered" (default): every tweak is a hypothesis fixed BEFORE seeing the
        data, so all of it can be used for one severe test per hypothesis, with Holm
        correction for how many we test (controls the chance of ANY fake discovery).
    design="split": for hypotheses generated FROM the data. Conjecture on the first part,
        pre-register suspects, then try to falsify them on unseen days (BH correction).
    """
    rng = np.random.default_rng(seed)
    tweaks = tweak_columns(df)
    out = {}

    # 1. separability
    blocked = set()
    for group in _inseparable_groups(df, tweaks):
        for t in group:
            others = ", ".join(g for g in group if g != t)
            out[t] = {"verdict": "not_sure", "p": float("nan"),
                      "reason": f"always changed together with {others}, so their effects can't be separated"}
            blocked.add(t)
    for t in tweaks:
        if t not in blocked and df[t].std() == 0:
            out[t] = {"verdict": "not_sure", "p": float("nan"), "reason": "never varied, nothing to compare"}
            blocked.add(t)
    testable = [t for t in tweaks if t not in blocked]

    # 2-3. trend removal + calendar controls. Primary measure = revenue from typical-sized
    # orders (outlier orders excluded) so a few unusual buyers can't create an effect.
    y_main = _detrend(df["revenue_excl_outliers"].to_numpy(float))
    y_raw = _detrend(df["revenue"].to_numpy(float))

    def explain_fake(t, part, r_raw, default):
        # visible in raw totals but not in typical orders -> driven by unusual buyers
        if _perm_p(r_raw, part[t].to_numpy(), rng) < 0.01:
            return ("only shows up in outlier-sized orders: likely a few unusual buyers, "
                    "not a real change in customer behaviour")
        return default

    if design == "preregistered":
        r = _calendar_residuals(y_main, df)
        r_raw = _calendar_residuals(y_raw, df)
        ps = [_perm_p(r, df[t].to_numpy(), rng) for t in testable]
        if testable:
            ok, adj, _, _ = multipletests(ps, alpha=ALPHA, method="holm")
        else:
            ok, adj = [], []
        for t, o, p in zip(testable, ok, adj):
            if o:
                out[t] = {"verdict": "real", "p": float(p),
                          "reason": "survived a severe test: trend and calendar controls, outlier-proof "
                                    "measure, Holm correction for testing every tweak"}
            else:
                out[t] = {"verdict": "fake", "p": float(p),
                          "reason": explain_fake(t, df, r_raw,
                                                 "not strong enough once we correct for testing every tweak")}
        if verbose:
            print(f"  Pre-registered hypotheses: all {len(testable)} tweaks, before looking at results")
            for t in testable:
                if out[t]["verdict"] == "real" or out[t]["reason"].startswith("only shows up"):
                    print(f"    {t:16s} -> {out[t]['verdict'].upper():8s} {out[t]['reason']}")
            for t in sorted(blocked):
                print(f"    {t:16s} -> NOT SURE {out[t]['reason']}")
        return out

    # ---- design == "split"
    cut = int(len(df) * explore_frac)
    explore, hold = df.iloc[:cut], df.iloc[cut:]
    r_explore = _calendar_residuals(y_main[:cut], explore)
    r_hold = _calendar_residuals(y_main[cut:], hold)
    r_explore_raw = _calendar_residuals(y_raw[:cut], explore)

    explore_p = {t: _perm_p(r_explore, explore[t].to_numpy(), rng) for t in testable}
    suspects = [t for t in testable if explore_p[t] < explore_alpha]
    if verbose:
        print(f"  Pre-registered suspects (days 1-{cut}, before looking at days {cut + 1}-{len(df)}): "
              f"{suspects or 'none'}")
    for t in testable:
        if t not in suspects:
            out[t] = {"verdict": "fake", "p": explore_p[t],
                      "reason": explain_fake(t, explore, r_explore_raw,
                                             "no sign of an effect even on the exploration days")}
    if suspects:
        hold_p = [_perm_p(r_hold, hold[t].to_numpy(), rng) for t in suspects]
        survived, adj, _, _ = multipletests(hold_p, alpha=ALPHA, method="fdr_bh")
        for t, p, ok in zip(suspects, adj, survived):
            out[t] = ({"verdict": "real", "p": float(p),
                       "reason": "survived unseen days, multiple-testing correction, trend and calendar controls"}
                      if ok else
                      {"verdict": "fake", "p": float(p),
                       "reason": "looked promising at first but vanished on unseen days"})
    if verbose:
        for t in testable:
            if t in suspects or out[t]["reason"].startswith("only shows up"):
                print(f"    {t:16s} -> {out[t]['verdict'].upper():8s} {out[t]['reason']}")
        for t in sorted(blocked):
            print(f"    {t:16s} -> NOT SURE {out[t]['reason']}")
    return out
