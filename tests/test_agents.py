"""backend/agents.py: the live game's naive AI and careful AI (evidence-only decision)."""
import dataclasses

import numpy as np
import pytest

from backend.agents import (E_BAR, LIFT_GRID, BaselineModel, CarefulAgent, _e_value,
                            _log_lik_ratios, naive_window)
from backend.game import PAST_HOURS
from backend.simulator2 import Shop

VERDICTS = {"REAL", "FAKE"}
LABELS = {"IT WORKED!", "NO REAL LIFT"}   # two answers only, never "not sure"


def trained(seed=1, effect=0.20):
    shop = Shop(seed=seed, good_effect=effect)
    shop.run(PAST_HOURS)
    return shop, CarefulAgent(shop.history)


def window(shop, kind, hours=24):
    return [shop.step(kind) for _ in range(hours)]


# ---- the maths ---------------------------------------------------------------- #

def test_bar_is_one_over_five_percent():
    assert E_BAR == pytest.approx(20)


def test_no_evidence_gives_e_value_one():
    assert _e_value(np.zeros(len(LIFT_GRID))) == pytest.approx(1.0)


def test_e_value_grows_with_more_customers():
    exp = 300.0
    assert _e_value(_log_lik_ratios(360, exp, 1.0)) > _e_value(_log_lik_ratios(320, exp, 1.0)) > \
        _e_value(_log_lik_ratios(300, exp, 1.0))


def test_e_value_is_valid_under_a_useless_offer():
    """Markov: if the offer does nothing, the e-value reaches 20 in at most ~5% of windows."""
    rng = np.random.default_rng(0)
    exp = 300.0
    hits = [_e_value(_log_lik_ratios(int(rng.poisson(exp)), exp, 1.0)) >= E_BAR for _ in range(20000)]
    assert np.mean(hits) <= 0.05


def test_noisier_data_means_weaker_evidence():
    assert _e_value(_log_lik_ratios(360, 300.0, 3.0)) < _e_value(_log_lik_ratios(360, 300.0, 1.0))


# ---- what it learns and what it sees ---------------------------------------------- #

def test_baseline_learned_from_past_sales_is_close_to_truth():
    shop, agent = trained(seed=2)
    recs = shop.run(200)
    errors = [abs(agent.model.expected(r.ai_view()) / r.expected_customers - 1) for r in recs]
    assert sum(errors) / len(errors) < 0.08


def test_baseline_only_uses_no_offer_hours():
    shop = Shop(seed=3)
    shop.run(PAST_HOURS)
    shop.step("good")
    assert BaselineModel([r.ai_view() for r in shop.history]).n_hours == PAST_HOURS


def test_ai_view_hides_which_offer_and_the_truth():
    rec = Shop(seed=4).step("bad").ai_view()
    assert rec["action"] == "offer"
    assert not {"expected_customers", "true_effect", "offer_is_real", "friends", "is_rush_hour"} & set(rec)


def test_careful_ai_never_reads_the_hidden_truth():
    """Corrupt every hidden field and swap good<->bad labels: the verdict must not change."""
    shop, a1 = trained(seed=5)
    _, a2 = trained(seed=5)
    for kind in ("good", "bad", "good", "bad"):
        recs = window(shop, kind)
        poisoned = [dataclasses.replace(r, expected_customers=1e9, true_effect=99.0,
                                        offer_is_real=not r.offer_is_real,
                                        action="bad" if r.action == "good" else "good") for r in recs]
        out1, out2 = a1.judge_window(recs), a2.judge_window(poisoned)
        assert (out1["verdict"], out1["evidence"]) == (out2["verdict"], out2["evidence"])


def test_habits_never_decide_the_verdict():
    """The verdict is REAL exactly when the evidence passes the bar, whatever the gut feeling says."""
    shop, agent = trained(seed=6)
    for kind in ["good", "bad"] * 6:
        out = agent.judge_window(window(shop, kind))
        assert (out["verdict"] == "REAL") == (out["evidence"] >= E_BAR)
        # the label on screen is always a plain yes or no, matching the verdict
        assert out["label"] == ("IT WORKED!" if out["verdict"] == "REAL" else "NO REAL LIFT")


def test_verdict_format():
    shop, agent = trained(seed=7)
    out = agent.judge_window(window(shop, "good"))
    assert out["verdict"] in VERDICTS and out["label"] in LABELS and out["text"]
    for key in ("evidence", "evidenceNeeded", "probability", "expected", "seen", "hours"):
        assert key in out


def test_naive_ai_fooled_by_a_busy_window():
    shop, _ = trained(seed=8)
    shop.trigger_event("tiktok_viral")
    past = list(shop.history)
    busy = window(shop, "bad", hours=3)
    assert naive_window(busy, past)["verdict"] in VERDICTS
