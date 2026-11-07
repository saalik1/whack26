"""backend/defender.py: naive vs Popper researcher on the daily shop.
Fixed seeds (60000+) that were never used for tuning, so results are deterministic."""
import numpy as np
import pytest

from backend.defender import _perm_p, naive_researcher, popper_researcher
from backend.simulator import CHEAT_TARGET, CHEATS, simulate

SEED = 60000
GAMES = 15
VERDICTS = {"real", "fake", "not_sure"}


def fakes(result, truth):
    return [k for k, v in result.items() if v["verdict"] == "real" and truth[k] == 0]


@pytest.mark.parametrize("design", ["preregistered", "split"])
def test_verdict_format(design):
    df, truth = simulate(1, cheat="confounder")
    for researcher in (naive_researcher(df), popper_researcher(df, 1, design=design)):
        assert set(researcher) == set(truth)
        for v in researcher.values():
            assert v["verdict"] in VERDICTS
            assert isinstance(v["reason"], str) and v["reason"]


def test_permutation_test_sanity():
    rng = np.random.default_rng(0)
    flag = np.array([0, 1] * 30)
    same = rng.normal(0, 1, 60)
    shifted = same + 3 * flag
    assert _perm_p(same, flag, rng) > 0.05
    assert _perm_p(shifted, flag, rng) < 0.001


def test_too_few_observations_gives_p_of_one():
    rng = np.random.default_rng(0)
    assert _perm_p(np.arange(10.0), np.array([1, 1] + [0] * 8), rng) == 1.0


def test_pure_noise_popper_rarely_declares_anything():
    popper_hits = naive_hits = 0
    for g in range(GAMES):
        df, _ = simulate(SEED + 100 + g, pure_noise=True)
        popper_hits += any(v["verdict"] == "real" for v in popper_researcher(df, g).values())
        naive_hits += any(v["verdict"] == "real" for v in naive_researcher(df).values())
    assert popper_hits <= 3            # design level is ~5% per game
    assert naive_hits > popper_hits     # 20+ tweaks at p<0.05: the naive AI "finds" things in noise


@pytest.mark.parametrize("cheat", CHEATS)
def test_cheat_fools_naive_but_not_popper(cheat):
    target = CHEAT_TARGET.get(cheat)
    naive_fooled = popper_fooled = found = 0
    for g in range(GAMES):
        df, truth = simulate(SEED + g, cheat=cheat)
        n, p = fakes(naive_researcher(df), truth), fakes(popper_researcher(df, g), truth)
        naive_fooled += (target in n) if target else bool(n)
        popper_fooled += (target in p) if target else bool(p)
        found += popper_researcher(df, g)["discount_10pct"]["verdict"] == "real"
    assert naive_fooled >= 3, f"{cheat}: the cheat should fool the naive AI"
    assert popper_fooled <= 1, f"{cheat}: our AI should almost never be fooled"
    assert naive_fooled > popper_fooled
    assert found >= (10 if cheat == "peeking" else 12), f"{cheat}: our AI should still find the real discount"


def test_confounded_tweaks_are_not_sure():
    df, _ = simulate(SEED, cheat="confounder")
    res = popper_researcher(df, 0)
    assert res["loyalty_points"]["verdict"] == "not_sure"
    assert res["new_music"]["verdict"] == "not_sure"
    assert "together" in res["new_music"]["reason"]


def test_fake_customers_explained_as_outliers():
    explained = 0
    for g in range(5):
        df, _ = simulate(SEED + g, cheat="fake_customers")
        explained += "outlier" in popper_researcher(df, g)["influencer_post"]["reason"]
    assert explained >= 3


def test_same_inputs_same_verdicts():
    df, _ = simulate(SEED, cheat="seasonality")
    a = {k: v["verdict"] for k, v in popper_researcher(df, 7).items()}
    b = {k: v["verdict"] for k, v in popper_researcher(df, 7).items()}
    assert a == b
