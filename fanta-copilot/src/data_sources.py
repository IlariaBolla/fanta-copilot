"""Polite, best-effort public source readers. No source is used during live bidding."""
from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
import re

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .config import FBREF_URL, HISTORY_STATS_URL, SOURCE_URL, STATS_URL
from .normalization import name_score, normalize_name

HEADERS = {
    "User-Agent": "FantaAuctionCopilot/1.0 (single-user educational app; contact via repository)"
}


def _integer(node) -> int:
    if node is None:
        return 0
    match = re.search(r"-?\d+", node.get_text(" ", strip=True))
    return int(match.group()) if match else 0


def _decimal(node) -> float:
    if node is None:
        return 0.0
    value = node.get_text(" ", strip=True).replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    return float(match.group()) if match else 0.0


def fetch_fantacalcio(timeout: int = 20) -> pd.DataFrame:
    response = requests.get(SOURCE_URL, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    updated = datetime.now(timezone.utc).isoformat()
    records = []
    for row in soup.select("tr.player-row"):
        link = row.select_one("a.player-link")
        name = row.get("data-filter-keywords") or (link.get_text(" ", strip=True) if link else "")
        if not name:
            continue
        href = link.get("href", "") if link else ""
        numeric_id = href.rstrip("/").split("/")[-1] if href else str(row.get("data-index", ""))
        mantra = row.get("data-filter-role-mantra", "").upper().replace(",", ";")
        records.append(
            {
                "player_id": f"fc-{numeric_id}",
                "name": name.strip(),
                "normalized_name": normalize_name(name),
                "team": (row.select_one("[data-col-key='sq']").get_text(strip=True) if row.select_one("[data-col-key='sq']") else ""),
                "role_classic": row.get("data-filter-role-classic", "").upper(),
                "roles_mantra": mantra,
                "quotation_classic": _integer(row.select_one("[data-col-key='c_qa']")),
                "quotation_mantra": _integer(row.select_one("[data-col-key='m_qa']")),
                "fvm_classic": _integer(row.select_one("[data-col-key='c_fvm']")),
                "fvm_mantra": _integer(row.select_one("[data-col-key='m_fvm']")),
                "appearances": 0,
                "starts": 0,
                "minutes": 0,
                "goals": 0,
                "assists": 0,
                "average_rating": 0.0,
                "fantasy_average": 0.0,
                "penalties_scored": 0,
                "penalties_taken": 0,
                "previous_appearances": 0,
                "previous_average_rating": 0.0,
                "previous_fantasy_average": 0.0,
                "previous_goals": 0,
                "previous_assists": 0,
                "starter_signal": "",
                "set_piece_signal": "",
                "injury_signal": "",
                "updated_at": updated,
            }
        )
    frame = pd.DataFrame(records)
    if len(frame) < 300:
        raise ValueError(f"Fantacalcio ha restituito solo {len(frame)} righe")
    return frame.drop_duplicates("player_id").reset_index(drop=True)


def fetch_fantacalcio_stats(timeout: int = 20, url: str = STATS_URL,
                            season: str = "2026-27") -> pd.DataFrame:
    """Season appearances and output from Fantacalcio's public table."""
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    records = []
    for row in soup.select("tr.player-row"):
        link = row.select_one("a.player-link")
        if not link:
            continue
        href = link.get("href", "")
        parts = href.rstrip("/").split("/")
        try:
            season_index = parts.index(season)
            numeric_id = parts[season_index - 1]
        except (ValueError, IndexError):
            numeric_id = ""
        penalties = (row.select_one("[data-col-key='rig']").get_text(strip=True)
                     if row.select_one("[data-col-key='rig']") else "0 / 0")
        penalty_numbers = [int(x) for x in re.findall(r"\d+", penalties)]
        records.append({
            "player_id": f"fc-{numeric_id}" if numeric_id else "",
            "stats_name": row.get("data-filter-keywords", ""),
            "appearances": _integer(row.select_one("[data-col-key='pg']")),
            "average_rating": _decimal(row.select_one("[data-col-key='mv']")),
            "fantasy_average": _decimal(row.select_one("[data-col-key='mfv']")),
            "goals": _integer(row.select_one("[data-col-key='gol']")),
            "assists": _integer(row.select_one("[data-col-key='ass']")),
            "penalties_scored": penalty_numbers[0] if penalty_numbers else 0,
            "penalties_taken": penalty_numbers[1] if len(penalty_numbers) > 1 else 0,
        })
    frame = pd.DataFrame(records)
    if len(frame) < 300:
        raise ValueError(f"Statistiche Fantacalcio: solo {len(frame)} righe")
    return frame[frame.player_id != ""].drop_duplicates("player_id")


def merge_fantacalcio_stats(players: pd.DataFrame, stats: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    columns = ["player_id", "appearances", "average_rating", "fantasy_average", "goals",
               "assists", "penalties_scored", "penalties_taken"]
    old = players.drop(columns=[c for c in columns[1:] if c in players], errors="ignore")
    merged = old.merge(stats[columns], how="left", on="player_id")
    for col in columns[1:]:
        merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0)
    matched = int(merged.player_id.isin(set(stats.player_id)).sum())
    unmatched = merged.loc[~merged.player_id.isin(set(stats.player_id)), "name"].tolist()
    return merged, {"source_rows": len(stats), "matched_players": matched,
                    "unmatched_players": unmatched, "ambiguous_matches": []}


def merge_historical_stats(players: pd.DataFrame, stats: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    mapping = {
        "appearances": "previous_appearances",
        "average_rating": "previous_average_rating",
        "fantasy_average": "previous_fantasy_average",
        "goals": "previous_goals",
        "assists": "previous_assists",
    }
    history = stats[["player_id"] + list(mapping)].rename(columns=mapping)
    old = players.drop(columns=list(mapping.values()), errors="ignore")
    merged = old.merge(history, how="left", on="player_id")
    for col in mapping.values():
        merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0)
    matched_ids = set(stats.player_id)
    matched = int(merged.player_id.isin(matched_ids).sum())
    unmatched = merged.loc[~merged.player_id.isin(matched_ids), "name"].tolist()
    return merged, {"source_rows": len(stats), "matched_players": matched,
                    "unmatched_players": unmatched, "ambiguous_matches": []}


def fetch_fbref(timeout: int = 20) -> pd.DataFrame:
    """Fetch just the standard player table. Failure is intentionally non-fatal."""
    response = requests.get(FBREF_URL, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    # FBref may wrap tables in comments; read_html handles both normal tables and
    # the uncommented copy after this conservative replacement.
    html = response.text.replace("<!--", "").replace("-->", "")
    tables = pd.read_html(StringIO(html))
    candidates = [t for t in tables if any("Player" in str(c) for c in t.columns)]
    if not candidates:
        raise ValueError("Tabella giocatori FBref non trovata")
    table = max(candidates, key=len)
    table.columns = [c[-1] if isinstance(c, tuple) else c for c in table.columns]
    table = table[table["Player"].astype(str) != "Player"].copy()
    rename = {"Player": "fbref_name", "Playing Time MP": "appearances", "MP": "appearances",
              "Starts": "starts", "Min": "minutes", "Gls": "goals", "Ast": "assists"}
    table = table.rename(columns=rename)
    wanted = [c for c in ["fbref_name", "appearances", "starts", "minutes", "goals", "assists"] if c in table]
    table = table.loc[:, ~table.columns.duplicated()][wanted]
    for col in ["appearances", "starts", "minutes", "goals", "assists"]:
        if col not in table:
            table[col] = 0
        table[col] = pd.to_numeric(table[col].astype(str).str.replace(",", ""), errors="coerce").fillna(0).astype(int)
    return table.drop_duplicates("fbref_name")


def merge_stats(players: pd.DataFrame, stats: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    result = players.copy()
    choices = stats["fbref_name"].astype(str).tolist()
    index = {str(row.fbref_name): row for row in stats.itertuples(index=False)}
    matched, unmatched, ambiguous = 0, [], []
    for i, player in result.iterrows():
        exact = [c for c in choices if normalize_name(c) == player["normalized_name"]]
        if len(exact) > 1:
            ambiguous.append({"player": player["name"], "candidates": exact[:3]})
            continue
        match = exact[0] if exact else None
        if not match:
            ranked = sorted(((name_score(player["name"], c), c) for c in choices), reverse=True)
            if ranked and ranked[0][0] >= .88:
                if len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= .035:
                    match = ranked[0][1]
                else:
                    ambiguous.append({"player": player["name"],
                                      "candidates": [ranked[0][1], ranked[1][1]]})
                    continue
        if not match:
            unmatched.append(player["name"])
            continue
        row = index[match]
        for col in ["appearances", "starts", "minutes", "goals", "assists"]:
            result.at[i, col] = int(getattr(row, col, 0))
        matched += 1
    report = {"source_rows": len(stats), "matched_players": matched,
              "unmatched_players": unmatched, "ambiguous_matches": ambiguous}
    return result, report
