"""backend/evidence_game.py: a small re-run of the peeking experiment."""
from backend.evidence_game import peeking


def test_checking_every_round_hurts_p_values_not_e_values():
    res = peeking(games=150, hours=40)
    p_ever, e_ever = res["pvalue_every_round"][-1], res["evalue_every_round"][-1]
    assert p_ever > e_ever
    assert e_ever <= res["budget"] + 0.02
    assert p_ever >= 0.05


def test_forced_decision_ours_is_rarely_fooled_and_still_finds_big_effects():
    from backend.evidence_game import forced_decision
    res = forced_decision(games=60, hours=120, good_effect=0.20, seed=97000)
    assert res["fooled"]["ab_test_once"] > 0.8               # confounded by rush hours
    assert res["fooled"]["evalue_every_hour"] <= 0.05
    assert res["fooled"]["pvalue_every_hour"] > res["fooled"]["evalue_every_hour"]
    assert res["found"]["evalue_every_hour"] >= 0.85         # NOT SURE can't hide: it must find real effects
