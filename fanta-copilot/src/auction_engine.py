from __future__ import annotations

import math
from typing import Optional

import pandas as pd

from .models import Alternative, AuctionRecommendation
from .valuation import (assign_tiers, base_fair_value, clip, league_size_factor,
                        market_factor, player_signal_factor, role_budget_shares,
                        scarcity_factor)


class AuctionEngine:
    def __init__(self, players: pd.DataFrame, config: dict, managers: list[dict], purchases: list[dict]):
        self.players = players.copy()
        self.config = config
        self.managers = managers
        self.purchases = purchases
        self.sold_ids = {str(p["player_id"]) for p in purchases}
        self.players["tier"] = assign_tiers(self.players, config.get("mode", "Classic"))

    @property
    def user(self) -> str:
        return self.config.get("user_manager", "NOI")

    def user_purchases(self) -> list[dict]:
        return [p for p in self.purchases if p["manager"] == self.user]

    def counts(self, manager: str) -> dict[str, int]:
        result = {r: 0 for r in self.config["roster"]}
        for p in self.purchases:
            if p["manager"] == manager and p["role"] in result:
                result[p["role"]] += 1
        return result

    def budget_left(self, manager: Optional[str] = None) -> int:
        manager = manager or self.user
        for row in self.managers:
            if row["name"] == manager:
                return int(row["budget_left"])
        return int(self.config["initial_budget"])

    def max_spend_now(self) -> int:
        total_slots = sum(self.config["roster"].values())
        other_unfilled = max(total_slots - len(self.user_purchases()) - 1, 0)
        minimum_price = int(self.config.get("minimum_price", 1))
        return max(self.budget_left() - other_unfilled * minimum_price, 0)

    def role_full(self, role: str) -> bool:
        return self.counts(self.user).get(role, 0) >= int(self.config["roster"].get(role, 0))

    def player_strength(self, player: pd.Series) -> float:
        return (base_fair_value(player, self.config["initial_budget"], self.config.get("mode", "Classic"))
                * player_signal_factor(player))

    def role_strength(self, manager: str, role: str) -> float:
        total = 0.0
        for purchase in self.purchases:
            if purchase["manager"] != manager or purchase["role"] != role:
                continue
            try:
                total += self.player_strength(self._player(str(purchase["player_id"])))
            except KeyError:
                total += float(purchase.get("baseline_fair", 0))
        return total

    def strongest_opponent(self, role: str) -> tuple[Optional[str], float]:
        ranked = [(m["name"], self.role_strength(m["name"], role))
                  for m in self.managers if m["name"] != self.user]
        return max(ranked, key=lambda item: item[1]) if ranked else (None, 0.0)

    def need_factor(self, player: pd.Series) -> float:
        role = player.role_classic
        slots = int(self.config["roster"].get(role, 0))
        filled = self.counts(self.user).get(role, 0)
        if filled >= slots:
            return 0.0
        tier = player.tier
        factor = 1.0
        if tier in {"S", "A"} and filled == 0:
            factor += 0.06
        if slots - filled == 1 and tier in {"C", "D"}:
            factor -= 0.06
        role_spend = sum(p["price"] for p in self.user_purchases() if p["role"] == role)
        shares = role_budget_shares(self.config.get("defense_modifier", "Non lo so"))
        planned = self.config["initial_budget"] * shares.get(role, .25)
        if role_spend > planned * 1.15 and tier not in {"S", "A"}:
            factor -= .06
        rival, rival_strength = self.strongest_opponent(role)
        our_strength = self.role_strength(self.user, role)
        if rival and rival_strength > 0 and our_strength < rival_strength * .70 and tier in {"S", "A"}:
            factor += .05
        elif rival_strength > 0 and our_strength > rival_strength * 1.25 and tier in {"C", "D"}:
            factor -= .03
        return clip(factor, .90, 1.08)

    def opportunity_factor(self, player: pd.Series) -> float:
        col = "fvm_mantra" if self.config.get("mode") == "Mantra" else "fvm_classic"
        pool = self.players[(self.players.role_classic == player.role_classic) &
                            (~self.players.player_id.astype(str).isin(self.sold_ids))]
        comparable = pool[(pool[col] >= float(player[col]) * .75) &
                          (pool[col] <= float(player[col]) * 1.30)]
        alternatives = max(len(comparable) - 1, 0)
        if alternatives <= 1:
            return 1.04
        if alternatives <= 3:
            return 1.02
        if alternatives >= 8:
            return .97
        return 1.0

    def rules_factor(self, player: pd.Series) -> float:
        role = str(player.role_classic)
        tier = str(player.tier)
        factor = 1.0
        if self.config.get("defense_modifier") == "Sì":
            if role == "D":
                factor += .055 if tier in {"S", "A"} else .02
            elif role == "P":
                factor += .025
        if self.config.get("clean_sheet_bonus") == "Sì" and role == "P":
            factor += .045
        return clip(factor, 1.0, 1.08)

    def opponent_pressure_factor(self, player_or_role) -> float:
        if isinstance(player_or_role, str):
            role, premium = player_or_role, False
        else:
            role = player_or_role.role_classic
            premium = str(player_or_role.tier) in {"S", "A"}
        opponents = [m for m in self.managers if m["name"] != self.user]
        if not opponents:
            return 1.0
        viable = 0.0
        for manager in opponents:
            needs = self.counts(manager).get(role, 0) < self.config["roster"].get(role, 0)
            if premium:
                premium_owned = 0
                for purchase in self.purchases:
                    if purchase["manager"] == manager["name"] and purchase["role"] == role:
                        try:
                            premium_owned += str(self._player(purchase["player_id"]).tier) in {"S", "A"}
                        except KeyError:
                            pass
                premium_quota = max(1, round(self.config["roster"].get(role, 1) * .25))
                needs = needs and premium_owned < premium_quota
            budget_ratio = manager["budget_left"] / max(manager["initial_budget"], 1)
            if needs:
                viable += budget_ratio
        pressure = viable / len(opponents)
        return clip(0.96 + 0.08 * pressure, 0.96, 1.04)

    def _context_value(self, player: pd.Series) -> tuple[float, dict]:
        base = base_fair_value(player, self.config["initial_budget"], self.config.get("mode", "Classic"))
        scarcity = scarcity_factor(player, self.players, self.sold_ids, self.config.get("mode", "Classic"))
        market, observed = market_factor(self.purchases, player.role_classic)
        components = {
            "base": base,
            "league": league_size_factor(int(self.config["participants"])),
            "signal": player_signal_factor(player),
            "need": self.need_factor(player),
            "scarcity": scarcity,
            "market": market,
            "observed_market": observed,
            "opponents": self.opponent_pressure_factor(player),
            "opportunity": self.opportunity_factor(player),
            "rules": self.rules_factor(player),
        }
        rival, rival_strength = self.strongest_opponent(player.role_classic)
        components["rival"] = rival
        components["rival_gap"] = max(rival_strength - self.role_strength(self.user, player.role_classic), 0)
        value = base
        for key in ["league", "signal", "need", "scarcity", "market", "opponents", "opportunity", "rules"]:
            value *= components[key]
        return value, components

    def baseline_fair(self, player_id: str) -> float:
        player = self._player(player_id)
        return base_fair_value(player, self.config["initial_budget"], self.config.get("mode", "Classic")) * league_size_factor(int(self.config["participants"]))

    def _player(self, player_id: str) -> pd.Series:
        rows = self.players[self.players.player_id.astype(str) == str(player_id)]
        if rows.empty:
            raise KeyError(player_id)
        return rows.iloc[0]

    def alternatives(self, player: pd.Series, limit: int = 3) -> list[Alternative]:
        pool = self.players[(self.players.role_classic == player.role_classic) &
                            (~self.players.player_id.astype(str).isin(self.sold_ids)) &
                            (self.players.player_id.astype(str) != str(player.player_id))].copy()
        fvm_col = "fvm_mantra" if self.config.get("mode") == "Mantra" else "fvm_classic"
        pool["distance"] = (pool[fvm_col] - player[fvm_col]).abs()
        result = []
        for _, alt in pool.sort_values(["distance", fvm_col], ascending=[True, False]).head(limit).iterrows():
            value, _ = self._context_value(alt)
            minimum_price = int(self.config.get("minimum_price", 1))
            result.append(Alternative(str(alt.player_id), alt["name"],
                                      min(max(math.ceil(value * 1.08), minimum_price), self.max_spend_now())))
        return result

    def recommend(self, player_id: str, current_price: int = 1) -> AuctionRecommendation:
        if str(player_id) in self.sold_ids:
            raise ValueError("Giocatore già acquistato.")
        player = self._player(player_id)
        full = self.role_full(player.role_classic)
        context, parts = self._context_value(player)
        fair = base_fair_value(player, self.config["initial_budget"], self.config.get("mode", "Classic")) * parts["league"] * parts["signal"]
        minimum_price = int(self.config.get("minimum_price", 1))
        target = max(minimum_price, math.floor(context * 0.92))
        hard = max(target + 1, math.ceil(context * 1.08))
        hard = min(hard, self.max_spend_now())
        target = min(target, max(hard - 1, 0))
        if full or hard < 1:
            action, target, hard = "🔴 PASSA", 0, 0
        elif current_price > hard:
            action = "🔴 PASSA"
        elif current_price > target:
            action = "🟡 RILANCIA CON CAUTELA"
        else:
            action = "🟢 COMPRA / RILANCIA"
        reasons = self._reasons(player, current_price, target, hard, parts, full)
        enriched = any(float(player.get(c, 0) or 0) for c in ["appearances", "minutes", "goals", "assists"])
        return AuctionRecommendation(str(player.player_id), player["name"], action, int(current_price), round(fair, 1),
                                     int(target), int(hard), str(player.tier), "Alta" if enriched else "Buona",
                                     [] if full else self.alternatives(player), reasons)

    def _reasons(self, player, price, target, hard, parts, full):
        if full:
            return [{"code": "BUDGET", "text": f"Il reparto {player.role_classic} è già completo."}]
        candidates = []
        candidates.append((3, "VALUE", "È ancora sotto il prezzo target." if price <= target else "Il prezzo ha superato il target conveniente."))
        if parts["need"] > 1.02:
            candidates.append((4, "NEED", f"Ti serve ancora un giocatore forte nel reparto {player.role_classic}."))
        if parts["scarcity"] > 1.025:
            candidates.append((4, "SCARCITY", "Restano poche alternative di valore simile."))
        if parts["observed_market"] > 1.10:
            candidates.append((3, "MARKET", "Gli altri stanno pagando troppo: non inseguire il mercato."))
        elif parts["observed_market"] < .90:
            candidates.append((3, "MARKET", "Il mercato sta offrendo prezzi convenienti."))
        if parts["opponents"] < .99:
            candidates.append((2, "OPPONENTS", "Gli avversari hanno meno forza per rilanciare."))
        if parts.get("rival_gap", 0) > self.config["initial_budget"] * .04 and str(player.tier) in {"S", "A"}:
            candidates.append((4, "NEED", f"{parts['rival']} è più forte in questo reparto: qui puoi recuperare."))
        if parts["opportunity"] < 1:
            candidates.append((2, "ALTERNATIVES", "Ci sono ancora diverse alternative simili."))
        elif parts["opportunity"] > 1.02:
            candidates.append((3, "ALTERNATIVES", "Le alternative dello stesso livello sono quasi finite."))
        if parts.get("rules", 1) > 1.02:
            candidates.append((3, "RULES", "Le regole della tua lega aumentano il valore di questo profilo."))
        candidates.append((2, "BUDGET", f"Lo stop lascia i crediti minimi per completare la rosa."))
        return [{"code": code, "text": text} for _, code, text in sorted(candidates, reverse=True)[:4]]

    def available_ranked(self, role: str, limit: int = 15) -> list[AuctionRecommendation]:
        pool = self.players[(self.players.role_classic == role) & (~self.players.player_id.astype(str).isin(self.sold_ids))]
        col = "fvm_mantra" if self.config.get("mode") == "Mantra" else "fvm_classic"
        return [self.recommend(str(row.player_id), 1) for _, row in pool.sort_values(col, ascending=False).head(limit).iterrows()]

    def squad_plan(self, limit: int = 3) -> list[dict]:
        """A small, opponent-aware next-move list for the non-expert user."""
        col = "fvm_mantra" if self.config.get("mode") == "Mantra" else "fvm_classic"
        role_labels = {"P": "Porta", "D": "Difesa", "C": "Centrocampo", "A": "Attacco"}
        plans = []
        for role, slots in self.config["roster"].items():
            filled = self.counts(self.user).get(role, 0)
            if filled >= slots:
                continue
            rival, rival_strength = self.strongest_opponent(role)
            ours = self.role_strength(self.user, role)
            gap = max(rival_strength - ours, 0)
            missing_ratio = (slots - filled) / max(slots, 1)
            strategic_weight = {"P": .02, "D": .04, "C": .08, "A": .14}.get(role, 0)
            score = missing_ratio * .45 + min(gap / max(self.config["initial_budget"] * .25, 1), .35) + strategic_weight
            pool = self.players[(self.players.role_classic == role) &
                                (~self.players.player_id.astype(str).isin(self.sold_ids))]
            if pool.empty:
                continue
            candidate = pool.sort_values(col, ascending=False).iloc[0]
            rec = self.recommend(str(candidate.player_id), 1)
            if rival and gap > self.config["initial_budget"] * .04:
                reason = f"{rival} ha già più qualità qui: è il reparto da recuperare."
            elif filled == 0 and role == "A":
                reason = "Ti manca ancora il riferimento principale per fare gol."
            else:
                reason = f"Hai ancora {slots - filled} posti da completare."
            plans.append({"role": role, "label": role_labels.get(role, role), "score": score,
                          "reason": reason, "player": rec.player, "tier": rec.tier,
                          "target": rec.target_price, "hard_stop": rec.hard_stop})
        return sorted(plans, key=lambda item: item["score"], reverse=True)[:limit]

    def remaining_budget_plan(self) -> dict[str, int]:
        """Allocate every remaining credit across incomplete roles."""
        counts = self.counts(self.user)
        minimum_price = int(self.config.get("minimum_price", 1))
        missing = {r: max(int(slots) - counts.get(r, 0), 0)
                   for r, slots in self.config["roster"].items()}
        minimums = {r: slots * minimum_price for r, slots in missing.items()}
        flexible = max(self.budget_left() - sum(minimums.values()), 0)
        shares = role_budget_shares(self.config.get("defense_modifier", "Non lo so"))
        role_spend = {r: sum(p["price"] for p in self.user_purchases() if p["role"] == r)
                      for r in missing}
        gaps = {r: max(self.config["initial_budget"] * shares.get(r, .25) - role_spend[r], 0)
                if missing[r] else 0 for r in missing}
        weight_total = sum(gaps.values())
        if weight_total <= 0:
            gaps = {r: shares.get(r, .25) if missing[r] else 0 for r in missing}
            weight_total = sum(gaps.values()) or 1
        raw = {r: minimums[r] + flexible * gaps[r] / weight_total for r in missing}
        result = {r: int(math.floor(value)) for r, value in raw.items()}
        remainder = self.budget_left() - sum(result.values())
        for role in sorted(raw, key=lambda r: raw[r] - result[r], reverse=True):
            if remainder <= 0:
                break
            if missing[role]:
                result[role] += 1
                remainder -= 1
        return result

    def purchase_impact(self, player_id: str, price: int) -> dict:
        player = self._player(player_id)
        remaining_slots = max(sum(self.config["roster"].values()) - len(self.user_purchases()) - 1, 0)
        minimum_price = int(self.config.get("minimum_price", 1))
        budget_after = self.budget_left() - int(price)
        reserve_needed = remaining_slots * minimum_price
        plan = self.remaining_budget_plan()
        role_budget_after = plan.get(player.role_classic, 0) - int(price)
        rival, rival_strength = self.strongest_opponent(player.role_classic)
        gap_before = max(rival_strength - self.role_strength(self.user, player.role_classic), 0)
        gap_after = max(gap_before - self.player_strength(player), 0)
        gap_closed = 0 if gap_before <= 0 else round((gap_before - gap_after) / gap_before * 100)
        return {
            "safe": int(price) <= self.max_spend_now(),
            "budget_after": budget_after,
            "remaining_slots": remaining_slots,
            "reserve_needed": reserve_needed,
            "role": player.role_classic,
            "role_budget_after": role_budget_after,
            "rival": rival,
            "gap_closed_percent": gap_closed,
        }
