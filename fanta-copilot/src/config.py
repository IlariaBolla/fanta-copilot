from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
PLAYERS_FILE = DATA_DIR / "current_players.csv"
METADATA_FILE = DATA_DIR / "metadata.json"
DB_FILE = DATA_DIR / "auction.sqlite3"

SEASON = "2026/27"
SOURCE_URL = "https://www.fantacalcio.it/quotazioni-fantacalcio/2026-27"
FBREF_URL = "https://fbref.com/en/comps/11/stats/Serie-A-Stats"
STATS_URL = "https://www.fantacalcio.it/statistiche-serie-a/2026-27/italia"
HISTORY_STATS_URL = "https://www.fantacalcio.it/statistiche-serie-a/2025-26/italia"
DEFAULT_ROSTER = {"P": 3, "D": 8, "C": 8, "A": 6}
ROLE_SHARES = {"P": 0.06, "D": 0.10, "C": 0.24, "A": 0.60}
MIN_PRICE = 1
REFRESH_HOURS = 6
