"""backend/agents.py: the live game's naive AI and careful AI (e-values)."""
import dataclasses
import math

import numpy as np
import pytest

from backend.agents import (ALPHA, E_THRESHOLD, OFFERS, BaselineModel, CarefulAgent,
                            _anytime_upper, _e_value, naive_agent)
from backend.game import PAST_HOURS
from backend.simulator2 import Shop

VERDICTS = {"REAL", "FAKE", "NOT SURE YET", "NO OFFER"}


def trained(seed=1, effect=0.20):
    shop = Shop(seed=seed, good_effect=effect)
    shop.run(PAST_HOURS)
    return shop, CarefulAgent(shop.history)


# ---- the maths ------------------------------------------------------------ #

def test_threshold_splits_the_error_budget():
    assert E_THRESHOLD == pytest.approx(len(OFFERS) / ALPHA) == pytest.approx(40)


def test_no_evidence_means_e_value_of_at_most_one():
    for n in (1, 10, 100):
        assert _e_value(0.0, n) <= 1.0


def test_e_value_grows_with_evidence():
    assert _e_value(5.0, 20) > _e_value(2.0, 20) > _e_value(0.0, 20)
    assert _e_value(-3.0, 20) < 1.0


def test_e_process_is_valid_under_the_null():
    """Ville's inequality: with no real effect, the e-value should cross 1/alpha
    at ANY point in 200 checks in at most ~alpha of runs, however often we look."""
    rng = np.random.default_rng(0)
    runs, steps, alpha = 4000, 200, 0.05
    S = np.cumsum(rng.normal(0, 1, (runs, steps)), axis=1)
    n = np.arange(1, steps + 1)
    v = 1 + n * 0.25
    e = 2 / np.sqrt(v) * np.exp(0.25 * S ** 2 / (2 * v)) * 0.5 * (1 + np.vectorize(math.erf)(0.5 * S / np.sqrt(v) / math.sqrt(2)))
    ever = (e >= 1 / alpha).any(axis=1).mean()
    assert ever <= alpha + 0.01


def test_confidence_range_shrinks_with_more_data():
    assert _anytime_upper(0.0, 400, 0.025) < _anytime_upper(0.0, 40, 0.025) < _anytime_upper(0.0, 4, 0.025)


# ---- the baseline it learns -------------------------------------------------- #

def test_baseline_learned_from_past_sales_is_close_to_truth():
    shop, agent = trained(seed=2)
    recs = shop.run(200)
    errors = [abs(agent.model.expected(r.public()) / r.expected_customers - 1) for r in recs]
    assert sum(errors) / len(errors) < 0.08


def test_baseline_only_uses_no_offer_hours():
    shop = Shop(seed=3)
    shop.run(PAST_HOURS)
    shop.step("good")
    model = BaselineModel([r.public() for r in shop.history])
    assert model.n_hours == PAST_HOURS


def test_careful_ai_never_reads_the_hidden_truth():
    """Corrupt every hidden field: the verdicts must not change."""
    shop, a1 = trained(seed=4)
    _, a2 = trained(seed=4)
    for offer in ["bad", "good"] * 15:
        rec = shop.step(offer)
        poisoned = dataclasses.replace(rec, expected_customers=1e9, true_effect=99.0, offer_is_real=not rec.offer_is_real)
        assert a1.judge(rec) == a2.judge(poisoned)


# ---- behaviour ----------------------------------------------------------------- #

def test_one_hour_is_never_enough_to_say_real():
    for seed in range(20):
        shop, agent = trained(seed=100 + seed)
        assert agent.judge(shop.step("good"))["verdict"] != "REAL"


def test_no_offer_hours_are_not_judged():
    shop, agent = trained(seed=5)
    out = agent.judge(shop.step("none"))
    assert out["verdict"] == "NO OFFER"


def test_verdict_format():
    shop, agent = trained(seed=6)
    for offer in ("good", "bad", "none"):
        out = agent.judge(shop.step(offer))
        assert out["verdict"] in VERDICTS and out["label"] and out["text"]


def test_naive_ai_is_excited_by_rush_hours():
    shop = Shop(seed=7)
    shop.run(PAST_HOURS)
    fooled = 0
    for _ in range(60):
        rush = shop.forecast_next_hour()["is_rush_hour"]
        past = list(shop.history)
        rec = shop.step("bad" if rush else "none")
        if rec.action == "bad":
            fooled += naive_agent(rec, past)["verdict"] == "REAL"
    assert fooled >= 5


def test_falls_back_to_forecast_without_past_sales():
    shop = Shop(seed=8)
    agent = CarefulAgent([])
    assert agent.model is None
    assert agent.judge(shop.step("bad"))["verdict"] in VERDICTS
