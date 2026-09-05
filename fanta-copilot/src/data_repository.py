from __future__ import annotations

from datetime import datetime, timezone
import json

import pandas as pd

from .config import METADATA_FILE, PLAYERS_FILE, REFRESH_HOURS


REQUIRED_COLUMNS = [
    "player_id", "name", "normalized_name", "team", "role_classic", "roles_mantra",
    "quotation_classic", "quotation_mantra", "fvm_classic", "fvm_mantra",
    "appearances", "starts", "minutes", "goals", "assists", "average_rating",
    "fantasy_average", "penalties_scored", "penalties_taken", "starter_signal",
    "previous_appearances", "previous_average_rating", "previous_fantasy_average",
    "previous_goals", "previous_assists",
    "set_piece_signal", "injury_signal", "updated_at",
]


def load_players() -> pd.DataFrame:
    if not PLAYERS_FILE.exists():
        raise FileNotFoundError("Snapshot giocatori mancante. Esegui scripts/refresh_data.py")
    frame = pd.read_csv(PLAYERS_FILE, keep_default_na=False)
    missing = set(REQUIRED_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"Snapshot non valido; colonne mancanti: {sorted(missing)}")
    for col in ["quotation_classic", "quotation_mantra", "fvm_classic", "fvm_mantra",
                "appearances", "starts", "minutes", "goals", "assists", "average_rating",
                "fantasy_average", "penalties_scored", "penalties_taken",
                "previous_appearances", "previous_average_rating", "previous_fantasy_average",
                "previous_goals", "previous_assists"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0)
    return frame


def load_metadata() -> dict:
    if not METADATA_FILE.exists():
        return {"updated_at": "", "health": {"snapshot": "disponibile"}}
    return json.loads(METADATA_FILE.read_text(encoding="utf-8"))


def snapshot_is_stale() -> bool:
    stamp = load_metadata().get("updated_at")
    if not stamp:
        return True
    try:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        return age.total_seconds() > REFRESH_HOURS * 3600
    except ValueError:
        return True
