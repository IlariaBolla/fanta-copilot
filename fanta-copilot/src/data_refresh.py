from __future__ import annotations

from datetime import datetime, timezone
import json

from .config import (DATA_DIR, HISTORY_STATS_URL, METADATA_FILE, PLAYERS_FILE, SEASON,
                     SOURCE_URL, STATS_URL)
from .data_sources import (fetch_fantacalcio, fetch_fantacalcio_stats, fetch_fbref,
                           merge_fantacalcio_stats, merge_historical_stats, merge_stats)


def refresh_data(include_fbref: bool = True) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    health = {"fantacalcio_listone": "ok", "fantacalcio_statistiche": "non disponibile",
              "storico_2025_26": "non disponibile", "fbref": "non richiesto"}
    players = fetch_fantacalcio()
    current_report = {"source_rows": 0, "matched_players": 0,
                      "unmatched_players": [], "ambiguous_matches": []}
    history_report = dict(current_report)
    fbref_report = dict(current_report)
    try:
        current_stats = fetch_fantacalcio_stats()
        players, current_report = merge_fantacalcio_stats(players, current_stats)
        health["fantacalcio_statistiche"] = "ok"
    except Exception as exc:
        health["fantacalcio_statistiche"] = f"non disponibile: {type(exc).__name__}"
    try:
        history = fetch_fantacalcio_stats(url=HISTORY_STATS_URL, season="2025-26")
        players, history_report = merge_historical_stats(players, history)
        health["storico_2025_26"] = "ok"
    except Exception as exc:
        health["storico_2025_26"] = f"non disponibile: {type(exc).__name__}"
    if include_fbref:
        try:
            stats = fetch_fbref()
            players, fbref_report = merge_stats(players, stats)
            health["fbref"] = "ok"
        except Exception as exc:  # optional source
            health["fbref"] = f"non disponibile: {type(exc).__name__}"
    now = datetime.now(timezone.utc).isoformat()
    players["updated_at"] = now
    players.to_csv(PLAYERS_FILE, index=False)
    metadata = {
        "season": SEASON,
        "updated_at": now,
        "source_url": SOURCE_URL,
        "stats_url": STATS_URL,
        "history_stats_url": HISTORY_STATS_URL,
        "players": len(players),
        "health": health,
        "refresh_report": current_report,
        "historical_report": history_report,
        "fbref_report": fbref_report,
    }
    METADATA_FILE.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata
