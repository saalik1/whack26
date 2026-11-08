"""backend/evidence_game.py: a small re-run of the live-game evidence."""
from backend.evidence_game import evaluate


def test_small_rerun_matches_the_claims():
    res = evaluate(games=5, offers=8, effects=(0.20,), seed=150000)["results"]["20pct"]
    for strategy in ("random", "cheater", "switcher"):
        assert res[strategy]["ours"]["fooled"] <= 0.06
        assert res[strategy]["naive"]["fooled"] >= res[strategy]["ours"]["fooled"]
