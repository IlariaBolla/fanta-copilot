from __future__ import annotations

from statistics import median
from typing import Optional

import pandas as pd

from .config import ROLE_SHARES


def clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def fvm_column(mode: str) -> str:
    return "fvm_mantra" if mode.lower() == "mantra" else "fvm_classic"


def base_fair_value(player: pd.Series, initial_budget: int, mode: str = "Classic") -> float:
    return max(1.0, float(player.get(fvm_column(mode), 0)) * initial_budget / 1000.0)


def league_size_factor(participants: int) -> float:
    return clip(1.0 + (participants - 10) * 0.02, 0.92, 1.08)


def player_signal_factor(player: pd.Series) -> float:
    factor = 1.0
    starter = str(player.get("starter_signal", "")).lower()
    injury = str(player.get("injury_signal", "")).lower()
    set_piece = str(player.get("set_piece_signal", "")).lower()
    if starter in {"yes", "si", "sì", "probabile", "starter"}:
        factor += 0.035
    elif starter in {"no", "riserva", "rotation"}:
        factor -= 0.045
    if set_piece:
        factor += 0.025
    if injury:
        factor -= 0.06
    apps = float(player.get("appearances", 0) or 0)
    minutes = float(player.get("minutes", 0) or 0)
    goals = float(player.get("goals", 0) or 0)
    assists = float(player.get("assists", 0) or 0)
    average_rating = float(player.get("average_rating", 0) or 0)
    fantasy_average = float(player.get("fantasy_average", 0) or 0)
    # Early-season data is deliberately weak and bounded.
    if apps:
        factor += clip((minutes / apps - 45) / 1800, -0.02, 0.02)
        factor += clip((goals + assists) / max(apps, 1) * 0.015, 0, 0.025)
        if average_rating:
            factor += clip((average_rating - 6.0) * .018, -.025, .025)
        if fantasy_average:
            factor += clip((fantasy_average - 6.5) * .008, -.02, .035)
    previous_apps = float(player.get("previous_appearances", 0) or 0)
    previous_fantasy_average = float(player.get("previous_fantasy_average", 0) or 0)
    if previous_apps >= 5 and previous_fantasy_average:
        role_baseline = {"P": 5.4, "D": 6.1, "C": 6.5, "A": 7.0}.get(
            str(player.get("role_classic", "")), 6.4)
        reliability = min(previous_apps / 25.0, 1.0)
        factor += clip((previous_fantasy_average - role_baseline) * .018 * reliability,
                       -.045, .045)
        factor += .01 if previous_apps >= 28 else (-.01 if previous_apps < 10 else 0)
    return clip(factor, 0.90, 1.10)


def assign_tiers(players: pd.DataFrame, mode: str = "Classic") -> pd.Series:
    col = fvm_column(mode)
    result = pd.Series("D", index=players.index, dtype="object")
    for _, group in players.groupby("role_classic"):
        pct = group[col].rank(method="average", pct=True)
        tiers = pd.cut(pct, bins=[0, .40, .65, .82, .94, 1.0], labels=["D", "C", "B", "A", "S"], include_lowest=True)
        result.loc[group.index] = tiers.astype(str)
    return result


def scarcity_factor(player: pd.Series, all_players: pd.DataFrame, sold_ids: set[str], mode: str = "Classic") -> float:
    col = fvm_column(mode)
    role_pool = all_players[all_players.role_classic == player.role_classic]
    value = float(player[col])
    # Comparable players are at least 75% as valuable. This means the factor can
    # only rise (or stay flat) when a comparable option is sold.
    comparable = role_pool[role_pool[col] >= value * 0.75]
    initial = max(len(comparable), 1)
    remaining = max(len(comparable[~comparable.player_id.isin(sold_ids)]), 1)
    lost_ratio = 1 - remaining / initial
    return clip(1.0 + 0.14 * lost_ratio, 1.0, 1.14)


def market_factor(purchases: list[dict], role: Optional[str] = None) -> tuple[float, float]:
    usable = [p for p in purchases if float(p.get("baseline_fair", 0)) > 0]
    role_rows = [p for p in usable if p.get("role") == role]
    sample = role_rows if len(role_rows) >= 5 else usable
    if not sample:
        return 1.0, 1.0
    ratios = [float(p["price"]) / float(p["baseline_fair"]) for p in sample]
    observed = clip(median(ratios), 0.65, 1.45)
    shrink = len(sample) / (len(sample) + 10.0)
    estimated = 1.0 + (observed - 1.0) * shrink
    # Follow only half the adjusted market movement: discipline matters.
    applied = clip(1.0 + (estimated - 1.0) * 0.50, 0.90, 1.12)
    return applied, observed


def role_budget_shares(defense_modifier: str) -> dict[str, float]:
    shares = dict(ROLE_SHARES)
    if defense_modifier == "Sì":
        shares.update({"P": .075, "D": .135, "C": .23, "A": .56})
    return shares
