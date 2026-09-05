import pytest

from src.auction_engine import AuctionEngine
from src.persistence import AuctionStore


def test_hard_stop_preserves_completion_budget(players, config, managers):
    engine = AuctionEngine(players, config, managers, [])
    rec = engine.recommend(players[players.role_classic == "A"].iloc[0].player_id)
    other_slots = sum(config["roster"].values()) - 1
    assert rec.hard_stop <= config["initial_budget"] - other_slots


def test_sold_player_cannot_be_recommended(players, config, managers):
    player = players.iloc[0]
    purchase = {"player_id": player.player_id, "player_name": player["name"], "role": player.role_classic,
                "manager": "Marco", "price": 10, "baseline_fair": 10}
    with pytest.raises(ValueError):
        AuctionEngine(players, config, managers, [purchase]).recommend(player.player_id)


def test_full_role_is_pass(players, config, managers):
    config = {**config, "roster": {**config["roster"], "P": 1}}
    first, second = players[players.role_classic == "P"].iloc[:2].to_dict("records")
    purchases = [{"player_id": first["player_id"], "player_name": first["name"], "role": "P",
                  "manager": "NOI", "price": 10, "baseline_fair": 20}]
    managers[0].update(budget_left=490, players_bought=1)
    rec = AuctionEngine(players, config, managers, purchases).recommend(second["player_id"])
    assert rec.action == "🔴 PASSA" and rec.hard_stop == 0


def test_opponent_pressure_falls_after_competitors_spend(players, config, managers):
    engine_rich = AuctionEngine(players, config, managers, [])
    poor = [dict(m) for m in managers]
    poor[1]["budget_left"] = 20; poor[2]["budget_left"] = 30
    engine_poor = AuctionEngine(players, config, poor, [])
    assert engine_poor.opponent_pressure_factor("A") < engine_rich.opponent_pressure_factor("A")


def test_undo_restores_budget_and_availability(tmp_path, players, config):
    store = AuctionStore(tmp_path / "auction.db")
    store.save_config(config, ["NOI", "Marco"])
    player = players.iloc[0]
    store.record_purchase(player.player_id, player["name"], player.role_classic, "Marco", 50, 40)
    assert store.managers()[1]["budget_left"] == 450
    restored = store.undo_last()
    assert restored["player_id"] == player.player_id
    assert store.managers()[1]["budget_left"] == 500
    engine = AuctionEngine(players, config, store.managers(), store.purchases())
    assert player.player_id not in engine.sold_ids


def test_engine_values_scale_roughly_with_budget(players, config, managers):
    pid = players[players.role_classic == "A"].iloc[2].player_id
    low = AuctionEngine(players, config, managers, []).recommend(pid).hard_stop
    high_config = {**config, "initial_budget": 1000}
    high_managers = [{**m, "initial_budget": 1000, "budget_left": 1000} for m in managers]
    high = AuctionEngine(players, high_config, high_managers, []).recommend(pid).hard_stop
    assert 1.9 <= high / low <= 2.1


def test_opponent_star_purchase_changes_our_role_priority(players, config, managers):
    attackers = players[players.role_classic == "A"].sort_values("fvm_classic", ascending=False)
    star, next_best = attackers.iloc[0], attackers.iloc[1]
    before = AuctionEngine(players, config, managers, [])
    purchase = {"player_id": star.player_id, "player_name": star["name"], "role": "A",
                "manager": "Marco", "price": 180, "baseline_fair": 200}
    changed_managers = [dict(m) for m in managers]
    changed_managers[1].update(budget_left=320, players_bought=1)
    after = AuctionEngine(players, config, changed_managers, [purchase])
    assert after.need_factor(after._player(next_best.player_id)) > before.need_factor(before._player(next_best.player_id))
    assert after.squad_plan(1)[0]["role"] == "A"


def test_user_can_select_their_manager(tmp_path, config):
    store = AuctionStore(tmp_path / "identity.db")
    store.save_config(config, ["NOI", "Marco", "Luca"])
    store.set_user_manager("Marco")
    assert store.get_config()["user_manager"] == "Marco"


def test_custom_minimum_price_is_reserved(players, config, managers):
    custom = {**config, "minimum_price": 3}
    engine = AuctionEngine(players, custom, managers, [])
    rec = engine.recommend(players[players.role_classic == "A"].iloc[0].player_id)
    assert rec.hard_stop <= 500 - 24 * 3


def test_budget_plan_uses_every_remaining_credit(players, config, managers):
    engine = AuctionEngine(players, config, managers, [])
    plan = engine.remaining_budget_plan()
    assert sum(plan.values()) == 500
    assert plan["A"] > plan["C"] > plan["D"] > plan["P"]


def test_league_rules_change_relevant_values(players, config, managers):
    defender = players[players.role_classic == "D"].sort_values("fvm_classic", ascending=False).iloc[0]
    goalkeeper = players[players.role_classic == "P"].sort_values("fvm_classic", ascending=False).iloc[0]
    normal = AuctionEngine(players, config, managers, [])
    special_config = {**config, "defense_modifier": "Sì", "clean_sheet_bonus": "Sì"}
    special = AuctionEngine(players, special_config, managers, [])
    assert special.recommend(defender.player_id).hard_stop > normal.recommend(defender.player_id).hard_stop
    assert special.recommend(goalkeeper.player_id).hard_stop > normal.recommend(goalkeeper.player_id).hard_stop


def test_settings_can_resize_league_and_preserve_solvent_state(tmp_path, config):
    store = AuctionStore(tmp_path / "settings.db")
    store.save_config(config, ["NOI", "Marco", "Luca"])
    updated = {**config, "initial_budget": 1000, "minimum_price": 2}
    store.update_league_settings(updated, 5)
    assert len(store.managers()) == 5
    assert store.get_config()["initial_budget"] == 1000
    assert all(manager["budget_left"] == 1000 for manager in store.managers())
