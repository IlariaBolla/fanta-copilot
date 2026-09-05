from datetime import datetime
import html
from typing import Optional


ROLE_NAMES = {"P": "Portieri", "D": "Difensori", "C": "Centrocampisti", "A": "Attaccanti"}
TEAM_NAMES = {
    "ATA": "Atalanta", "BOL": "Bologna", "CAG": "Cagliari", "COM": "Como",
    "FIO": "Fiorentina", "FRO": "Frosinone", "GEN": "Genoa", "INT": "Inter",
    "JUV": "Juventus", "LAZ": "Lazio", "LEC": "Lecce", "MIL": "Milan",
    "MON": "Monza", "NAP": "Napoli", "PAR": "Parma", "ROM": "Roma",
    "SAS": "Sassuolo", "TOR": "Torino", "UDI": "Udinese", "VEN": "Venezia",
}


def team_name(code: str) -> str:
    return TEAM_NAMES.get(str(code).upper(), str(code))


def format_timestamp(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().strftime("%d/%m/%Y %H:%M")
    except (ValueError, AttributeError):
        return "non disponibile"


def player_card(name: str, team: str, role: str, price: Optional[int] = None) -> str:
    suffix = f"<strong>{int(price)} cr</strong>" if price is not None else ""
    return (f'<div class="mini-card"><span><b>{html.escape(name)}</b><br>'
            f'<small>{html.escape(team_name(team))} · {html.escape(role)}</small></span>{suffix}</div>')
