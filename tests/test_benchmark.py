"""backend/benchmark.py helpers and the saved results files."""
import json

import pandas as pd

from backend.benchmark import EVAL_SEED, TUNE_SEED, score, wilson
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_tuning_and_evaluation_use_different_games():
    assert EVAL_SEED - TUNE_SEED >= 10_000


def test_wilson_interval():
    lo, hi = wilson(0, 200)
    assert lo == 0 and 0 < hi < 0.03
    lo, hi = wilson(100, 200)
    assert lo < 0.5 < hi
    lo, hi = wilson(200, 200)
    assert hi == 1.0


def test_score_counts_target_and_discount():
    truth = {"discount_10pct": 80, "flash_sale": 0, "tweak_00": 0}
    result = {"discount_10pct": {"verdict": "real"}, "flash_sale": {"verdict": "real"},
              "tweak_00": {"verdict": "fake"}}
    s = score(result, truth, "promo_timing")
    assert s["fooled_by_cheat"] and s["discount_found"] and s["fakes"] == ["flash_sale"]


def test_results_csv_is_complete_and_sane():
    res = pd.read_csv(ROOT / "backend" / "results.csv").set_index("cheat")
    assert set(res.index) == {"none", "confounder", "seasonality", "promo_timing", "fake_customers", "peeking"}
    assert (res["naive_fooled"] > res["popper_fooled"]).all()
    assert (res["popper_fooled"] <= 0.08).all()
    assert (res["popper_discount_found"] >= 0.8).all()


def test_results_game_json_matches_the_claims():
    g = json.loads((ROOT / "backend" / "results_game.json").read_text())
    for strategy, r in g["results"]["20pct"].items():
        assert r["ours"]["fooled"] <= 0.02
        assert r["ours"]["found"] >= 0.85
        assert r["naive"]["fooled"] > r["ours"]["fooled"]
