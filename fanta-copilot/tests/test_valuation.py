import pandas as pd

from src.valuation import base_fair_value, market_factor, scarcity_factor


def test_credit_scaling(players):
    player = players[players.role_classic == "A"].iloc[0]
    assert base_fair_value(player, 1000) == 2 * base_fair_value(player, 500)


def test_inflation_and_deflation_learn_gradually():
    high = [{"price": 120, "baseline_fair": 100, "role": "A"} for _ in range(20)]
    low = [{"price": 70, "baseline_fair": 100, "role": "A"} for _ in range(20)]
    few = high[:2]
    assert market_factor(high, "A")[0] > market_factor(few, "A")[0] > 1
    assert market_factor(low, "A")[0] < 1


def test_scarcity_never_decreases_when_comparable_players_leave(players):
    candidate = players[(players.role_classic == "A") & (players.fvm_classic == 300)].iloc[0]
    before = scarcity_factor(candidate, players, set())
    sold = set(players[(players.role_classic == "A") & (players.fvm_classic >= 250)].player_id) - {candidate.player_id}
    after = scarcity_factor(candidate, players, sold)
    assert after >= before
