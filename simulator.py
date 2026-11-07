"""
Shop simulator with hidden truth and attacker cheats.

simulate(seed, cheat=None, pure_noise=False) -> (df, truth)
  df columns: day, weekday, is_payday, revenue, revenue_excl_outliers, one 0/1 column per tweak
  truth: {tweak: real effect in GBP}  (0 = the tweak does nothing)

Cheats (the attacker's toolkit):
  None / "none"     20 meaningless tweaks hoping one looks good by luck (always on)
  "confounder"      a fake tweak always switched on together with a real one
  "seasonality"     a fake tweak switched on more and more as sales trend upwards
  "promo_timing"    a fake tweak run mostly on paydays and Saturdays (naturally busy)
  "fake_customers"  a fake tweak whose days get a couple of big fake orders
  "peeking"         the attacker stops the experiment the first day it looks significant
"""
import numpy as np
import pandas as pd
from scipy import stats

N_DAYS = 90
BASELINE = 1000.0            # average daily revenue (GBP)
NOISE_SD = 60.0              # day-to-day randomness
WEEKLY = np.array([0, -40, -30, -20, 10, 90, 70])  # Mon..Sun
PAYDAY_BOOST = 150.0
PAYDAY_DAYS = (0, 14, 29)    # day % 30
ORDERS_PER_DAY = 40
OUTLIER_K = 2.0            # log-scale Tukey fence
REAL_EFFECTS = {"discount_10pct": 80.0}   # the only genuinely useful tweak (+8%)
N_FAKE_TWEAKS = 20

CHEATS = ["none", "confounder", "seasonality", "promo_timing", "fake_customers", "peeking"]
# which tweak each cheat is trying to sneak through as a "discovery"
CHEAT_TARGET = {"confounder": "new_music", "seasonality": "summer_menu",
                "promo_timing": "flash_sale", "fake_customers": "influencer_post",
                "peeking": "bundle_deal"}


def simulate(seed=None, cheat=None, pure_noise=False, n_fake=N_FAKE_TWEAKS):
    cheat = None if cheat in (None, "none") else cheat
    if cheat is not None and cheat not in CHEATS:
        raise ValueError(f"unknown cheat {cheat!r}; choose from {CHEATS}")
    rng = np.random.default_rng(seed)
    day = np.arange(N_DAYS)
    weekday = day % 7
    is_payday = np.isin(day % 30, PAYDAY_DAYS).astype(int)

    tweaks, truth = {}, {}

    def add(name, column, effect=0.0):
        tweaks[name] = np.asarray(column).astype(int)
        truth[name] = 0.0 if pure_noise else effect

    for name, eff in REAL_EFFECTS.items():
        add(name, rng.integers(0, 2, N_DAYS), eff)
    for i in range(n_fake):
        add(f"tweak_{i:02d}", rng.integers(0, 2, N_DAYS))

    trend = np.zeros(N_DAYS)
    if cheat == "confounder":
        lp = rng.integers(0, 2, N_DAYS)
        add("loyalty_points", lp, 60.0)
        add("new_music", lp.copy())                      # always changed together
    elif cheat == "seasonality":
        trend = 4.0 * np.maximum(0, day - 45)            # sales rise in the second half
        p_on = 0.1 + 0.8 * day / (N_DAYS - 1)
        add("summer_menu", rng.random(N_DAYS) < p_on)
    elif cheat == "promo_timing":
        busy = (is_payday == 1) | (weekday == 5)
        add("flash_sale", rng.random(N_DAYS) < np.where(busy, 0.85, 0.1))
    elif cheat == "fake_customers":
        add("influencer_post", rng.integers(0, 2, N_DAYS))
    elif cheat == "peeking":
        add("bundle_deal", rng.integers(0, 2, N_DAYS))

    genuine = (BASELINE + WEEKLY[weekday] + PAYDAY_BOOST * is_payday + trend
               + rng.normal(0, NOISE_SD, N_DAYS))
    for name, col in tweaks.items():
        genuine += col * truth[name]

    # split each day's genuine revenue into individual orders, then add any fake orders
    day_orders = []
    for d in range(N_DAYS):
        weights = rng.lognormal(0, 0.5, ORDERS_PER_DAY)
        orders = list(genuine[d] * weights / weights.sum())
        if cheat == "fake_customers" and tweaks["influencer_post"][d] and rng.random() < 0.7:
            orders += list(rng.uniform(150, 250, 2))
        day_orders.append(np.array(orders))
    revenue = np.array([o.sum() for o in day_orders])
    # Tukey outlier fence over ALL orders in the dataset, on the log scale because
    # order values are right-skewed: log(order) > Q3 + OUTLIER_K * IQR is an outlier.
    # The defender only ever sees the daily totals with and without outlier orders.
    every = np.log(np.concatenate(day_orders))
    q1, q3 = np.percentile(every, [25, 75])
    fence = np.exp(q3 + OUTLIER_K * (q3 - q1))
    excl_outliers = np.array([o[o <= fence].sum() for o in day_orders])

    df = pd.DataFrame({"day": day, "weekday": weekday, "is_payday": is_payday,
                       "revenue": revenue, "revenue_excl_outliers": excl_outliers, **tweaks})
    df.attrs["stopped_early"] = False

    if cheat == "peeking":
        # impatient attacker: check every day from day 20, stop at the first p < 0.05
        for t in range(20, N_DAYS):
            sub = df.iloc[: t + 1]
            on, off = sub.loc[sub["bundle_deal"] == 1, "revenue"], sub.loc[sub["bundle_deal"] == 0, "revenue"]
            if len(on) > 2 and len(off) > 2 and stats.ttest_ind(on, off).pvalue < 0.05:
                df = df.iloc[: t + 1].copy()
                df.attrs["stopped_early"] = True
                break
    return df, truth


def tweak_columns(df):
    return [c for c in df.columns
            if c not in ("day", "weekday", "is_payday", "revenue", "revenue_excl_outliers")]
