"""backend/simulator.py: the daily shop used for the evidence."""
import numpy as np
import pytest

from backend.simulator import CHEAT_TARGET, CHEATS, N_DAYS, simulate, tweak_columns


def test_shape_and_columns():
    df, truth = simulate(1)
    assert len(df) == N_DAYS
    for col in ("day", "weekday", "is_payday", "revenue", "revenue_excl_outliers"):
        assert col in df.columns
    assert set(tweak_columns(df)) == set(truth)


def test_same_seed_same_shop():
    a, _ = simulate(42, cheat="promo_timing")
    b, _ = simulate(42, cheat="promo_timing")
    assert a.equals(b)


def test_different_seed_different_shop():
    a, _ = simulate(1)
    b, _ = simulate(2)
    assert not np.allclose(a["revenue"], b["revenue"])


def test_only_the_discount_is_real():
    _, truth = simulate(3)
    real = [k for k, v in truth.items() if v != 0]
    assert real == ["discount_10pct"]


def test_pure_noise_has_no_real_effects():
    _, truth = simulate(4, pure_noise=True, cheat="confounder")
    assert all(v == 0 for v in truth.values())


@pytest.mark.parametrize("cheat", [c for c in CHEATS if c != "none"])
def test_each_cheat_adds_its_useless_target(cheat):
    df, truth = simulate(5, cheat=cheat)
    target = CHEAT_TARGET[cheat]
    assert target in df.columns
    assert truth[target] == 0


def test_unknown_cheat_is_rejected():
    with pytest.raises(ValueError):
        simulate(1, cheat="bribery")


def test_confounder_columns_are_identical():
    df, truth = simulate(6, cheat="confounder")
    assert (df["loyalty_points"] == df["new_music"]).all()
    assert truth["loyalty_points"] > 0 and truth["new_music"] == 0


def test_peeking_stops_early_only_after_day_20():
    stopped = 0
    for seed in range(40):
        df, _ = simulate(seed, cheat="peeking")
        if df.attrs["stopped_early"]:
            stopped += 1
            assert 21 <= len(df) < N_DAYS
        else:
            assert len(df) == N_DAYS
    assert stopped > 0, "the impatient attacker should sometimes get lucky"


def test_outlier_free_revenue_never_exceeds_revenue():
    df, _ = simulate(7, cheat="fake_customers")
    assert (df["revenue_excl_outliers"] <= df["revenue"] + 1e-9).all()


def test_fake_customers_only_inflate_raw_revenue():
    df, _ = simulate(8, cheat="fake_customers")
    gap = df["revenue"] - df["revenue_excl_outliers"]
    on, off = gap[df["influencer_post"] == 1].mean(), gap[df["influencer_post"] == 0].mean()
    assert on > off + 100, "fake big orders should sit in raw revenue, not in typical-order revenue"
