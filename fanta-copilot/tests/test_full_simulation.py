from scripts.simulate_auction import run_simulation


def test_complete_imaginary_auction_respects_all_constraints():
    result = run_simulation(verbose=False)
    assert result["events"] == 250
    assert result["user_counts"] == {"P": 3, "D": 8, "C": 8, "A": 6}
    assert result["user_budget_left"] >= 0
    assert result["duplicate_players"] == 0
    assert result["hard_stop_violations"] == 0
    assert result["opponent_need_after"] > result["opponent_need_before"]
