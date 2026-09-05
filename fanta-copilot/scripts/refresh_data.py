#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.data_refresh import refresh_data

if __name__ == "__main__":
    metadata = refresh_data(include_fbref=True)
    print(f"Snapshot aggiornato: {metadata['players']} giocatori, {metadata['updated_at']}")
    print(metadata["health"])
    print(metadata["refresh_report"])
