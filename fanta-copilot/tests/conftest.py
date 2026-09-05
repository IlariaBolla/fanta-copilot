import pandas as pd
import pytest


@pytest.fixture
def players():
    records = []
    values = {
        "P": [140, 80, 40, 15],
        "D": [220, 180, 140, 100, 60, 30],
        "C": [300, 250, 210, 170, 120, 70],
        "A": [400, 350, 300, 250, 180, 100, 50],
    }
    i = 0
    for role, fvms in values.items():
        for fvm in fvms:
            i += 1
            records.append({
                "player_id": f"p{i}", "name": f"Player {i}", "normalized_name": f"player {i}",
                "team": "TST", "role_classic": role, "roles_mantra": role,
                "quotation_classic": max(fvm // 10, 1), "quotation_mantra": max(fvm // 10, 1),
                "fvm_classic": fvm, "fvm_mantra": fvm, "appearances": 0, "starts": 0,
                "minutes": 0, "goals": 0, "assists": 0, "starter_signal": "",
                "set_piece_signal": "", "injury_signal": "", "updated_at": "2026-09-04T12:00:00+00:00",
            })
    return pd.DataFrame(records)


@pytest.fixture
def config():
    return {"mode": "Classic", "participants": 10, "initial_budget": 500,
            "roster": {"P": 3, "D": 8, "C": 8, "A": 6},
            "defense_modifier": "Non lo so", "clean_sheet_bonus": "Non lo so", "user_manager": "NOI"}


@pytest.fixture
def managers():
    return [
        {"name": "NOI", "initial_budget": 500, "budget_left": 500, "players_bought": 0},
        {"name": "Marco", "initial_budget": 500, "budget_left": 500, "players_bought": 0},
        {"name": "Luca", "initial_budget": 500, "budget_left": 500, "players_bought": 0},
    ]
