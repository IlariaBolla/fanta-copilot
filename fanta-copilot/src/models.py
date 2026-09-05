from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Alternative:
    player_id: str
    name: str
    hard_stop: int


@dataclass
class AuctionRecommendation:
    player_id: str
    player: str
    action: str
    current_price: int
    fair_value: float
    target_price: int
    hard_stop: int
    tier: str
    confidence: str
    alternatives: list[Alternative] = field(default_factory=list)
    reasons: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class LeagueConfig:
    mode: str = "Classic"
    participants: int = 10
    initial_budget: int = 500
    roster: dict[str, int] = field(default_factory=lambda: {"P": 3, "D": 8, "C": 8, "A": 6})
    defense_modifier: str = "Non lo so"
    clean_sheet_bonus: str = "Non lo so"
    user_manager: str = "NOI"
