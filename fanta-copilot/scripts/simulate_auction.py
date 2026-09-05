#!/usr/bin/env python3
"""Deterministic full-auction simulation with imaginary players."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.auction_engine import AuctionEngine
from src.normalization import normalize_name
from src.persistence import AuctionStore
from src.valuation import market_factor, player_signal_factor


ROSTER = {"P": 3, "D": 8, "C": 8, "A": 6}
ROLE_NAMES = {"P": "Portiere", "D": "Difensore", "C": "Centrocampista", "A": "Attaccante"}


def imaginary_players() -> pd.DataFrame:
    sizes = {"P": 50, "D": 140, "C": 140, "A": 100}
    starts = {"P": 150, "D": 190, "C": 260, "A": 420}
    decay = {"P": 3.0, "D": 1.25, "C": 1.65, "A": 3.6}
    rows = []
    player_number = 0
    for role, size in sizes.items():
        for rank in range(1, size + 1):
            player_number += 1
            fvm = max(round(starts[role] - (rank - 1) * decay[role]), 3)
            name = f"{ROLE_NAMES[role]} Immaginario {rank:03d}"
            rows.append({
                "player_id": f"sim-{player_number}", "name": name,
                "normalized_name": normalize_name(name), "team": f"SIM{rank % 20 + 1:02d}",
                "role_classic": role, "roles_mantra": role,
                "quotation_classic": max(round(fvm / 10), 1),
                "quotation_mantra": max(round(fvm / 10), 1),
                "fvm_classic": fvm, "fvm_mantra": fvm,
                "appearances": 2, "starts": 0, "minutes": 0,
                "goals": 1 if role == "A" and rank <= 12 else 0,
                "assists": 1 if role in {"C", "A"} and rank <= 10 else 0,
                "average_rating": 6.5 if rank <= size // 3 else 6.0,
                "fantasy_average": 7.0 if rank <= size // 3 else 6.1,
                "penalties_scored": 0, "penalties_taken": 0,
                "previous_appearances": 30 if rank <= size // 2 else 14,
                "previous_average_rating": 6.5 if rank <= size // 3 else 6.0,
                "previous_fantasy_average": ({"P": 5.8, "D": 6.5, "C": 7.0, "A": 8.0}[role]
                                             if rank <= size // 3 else 6.0),
                "previous_goals": 15 if role == "A" and rank <= 10 else 0,
                "previous_assists": 8 if role == "C" and rank <= 10 else 0,
                "starter_signal": "", "set_piece_signal": "", "injury_signal": "",
                "updated_at": "2026-09-05T12:00:00+00:00",
            })
    return pd.DataFrame(rows)


def _config(budget: int = 500) -> dict:
    return {"mode": "Classic", "participants": 10, "initial_budget": budget,
            "roster": dict(ROSTER), "defense_modifier": "Non lo so",
            "clean_sheet_bonus": "Non lo so", "user_manager": "Squadra Utente"}


def run_simulation(verbose: bool = True) -> dict:
    players = imaginary_players()
    manager_names = ["Squadra Utente"] + [f"Avversario {i}" for i in range(1, 10)]
    minimum_budget_seen = 500
    hard_stop_violations = 0
    with tempfile.TemporaryDirectory(prefix="fanta-simulation-") as folder:
        store = AuctionStore(Path(folder) / "auction.db")
        store.save_config(_config(), manager_names)

        # A direct interaction check: a rival buying the best attacker must
        # increase our need for the next elite attacker and change the plan.
        before = AuctionEngine(players, _config(), store.managers(), store.purchases())
        attackers = players[players.role_classic == "A"].sort_values("fvm_classic", ascending=False)
        star, next_star = attackers.iloc[0], attackers.iloc[1]
        need_before = before.need_factor(before._player(next_star.player_id))
        store.record_purchase(star.player_id, star["name"], "A", "Avversario 1", 180,
                              before.baseline_fair(star.player_id))
        after = AuctionEngine(players, _config(), store.managers(), store.purchases())
        need_after = after.need_factor(after._player(next_star.player_id))
        assert need_after > need_before
        assert after.squad_plan(1)[0]["role"] == "A"
        store.undo_last()

        # Complete all 250 roster slots. Every state is rebuilt as it would be
        # after a real Streamlit purchase.
        for role, slots in ROSTER.items():
            for round_number in range(slots):
                for manager_name in manager_names:
                    engine = AuctionEngine(players, _config(), store.managers(), store.purchases())
                    available = players[(players.role_classic == role) &
                                        (~players.player_id.isin(engine.sold_ids))]
                    assert not available.empty
                    candidate = available.sort_values("fvm_classic", ascending=False).iloc[0]
                    baseline = engine.baseline_fair(candidate.player_id)
                    market_ratio = 1.10 if round_number < max(1, slots // 3) else .88
                    proposed = max(1, round(baseline * market_ratio))
                    manager_budget = engine.budget_left(manager_name)
                    bought = sum(engine.counts(manager_name).values())
                    safe_max = manager_budget - (sum(ROSTER.values()) - bought - 1)
                    price = max(1, min(proposed, safe_max))
                    if manager_name == engine.user:
                        recommendation = engine.recommend(candidate.player_id, price)
                        if recommendation.hard_stop > engine.max_spend_now():
                            hard_stop_violations += 1
                        price = min(price, max(recommendation.hard_stop, 1))
                    store.record_purchase(candidate.player_id, candidate["name"], role,
                                          manager_name, price, baseline)
                    minimum_budget_seen = min(minimum_budget_seen, store.managers()[manager_names.index(manager_name)]["budget_left"])

        final_engine = AuctionEngine(players, _config(), store.managers(), store.purchases())
        final_counts = final_engine.counts(final_engine.user)
        assert final_counts == ROSTER
        assert final_engine.budget_left() >= 0
        assert minimum_budget_seen >= 0
        assert len(store.purchases()) == 250
        assert len({p["player_id"] for p in store.purchases()}) == 250
        assert hard_stop_violations == 0
        for manager in manager_names:
            assert final_engine.counts(manager) == ROSTER
            assert final_engine.budget_left(manager) >= 0

        high_history = players[players.role_classic == "A"].iloc[0].copy()
        neutral_history = high_history.copy()
        neutral_history["previous_appearances"] = 0
        neutral_history["previous_fantasy_average"] = 0
        assert player_signal_factor(high_history) > player_signal_factor(neutral_history)

        inflated = [{"price": 120, "baseline_fair": 100, "role": "A"} for _ in range(20)]
        deflated = [{"price": 75, "baseline_fair": 100, "role": "A"} for _ in range(20)]
        result = {
            "events": len(store.purchases()),
            "user_budget_left": final_engine.budget_left(),
            "user_counts": final_counts,
            "minimum_budget_seen": minimum_budget_seen,
            "duplicate_players": len(store.purchases()) - len({p["player_id"] for p in store.purchases()}),
            "hard_stop_violations": hard_stop_violations,
            "opponent_need_before": need_before,
            "opponent_need_after": need_after,
            "inflation_factor": round(market_factor(inflated, "A")[0], 3),
            "deflation_factor": round(market_factor(deflated, "A")[0], 3),
            "historical_signal_used": True,
        }
    if verbose:
        print("SIMULAZIONE ASTA COMPLETA — GIOCATORI IMMAGINARI")
        print(f"Eventi registrati: {result['events']} (10 squadre × 25 giocatori)")
        print(f"Rosa utente: {result['user_counts']}")
        print(f"Budget utente finale: {result['user_budget_left']} / 500")
        print(f"Budget minimo mai osservato: {result['minimum_budget_seen']}")
        print(f"Duplicati: {result['duplicate_players']} · violazioni hard stop: {result['hard_stop_violations']}")
        print(f"Reazione avversari: bisogno {result['opponent_need_before']:.2f} → {result['opponent_need_after']:.2f}")
        print(f"Mercato: inflazione {result['inflation_factor']} · deflazione {result['deflation_factor']}")
        print("Storico 2025/26: segnale verificato")
    return result


if __name__ == "__main__":
    run_simulation()
