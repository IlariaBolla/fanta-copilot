from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Optional, Union
import sqlite3

from .config import DB_FILE


class AuctionStore:
    def __init__(self, path: Union[Path, str] = DB_FILE):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init(self):
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS managers (
                    name TEXT PRIMARY KEY, initial_budget INTEGER NOT NULL, position INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS purchases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_id TEXT NOT NULL UNIQUE, player_name TEXT NOT NULL,
                    role TEXT NOT NULL, manager TEXT NOT NULL, price INTEGER NOT NULL,
                    baseline_fair REAL NOT NULL, created_at TEXT NOT NULL
                );
            """)

    def is_configured(self) -> bool:
        return self.get_config() is not None

    def get_config(self):
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key='config'").fetchone()
        return json.loads(row["value"]) if row else None

    def save_config(self, config: dict, manager_names: list[str]):
        clean_names = []
        for name in manager_names:
            name = str(name).strip()
            if name and name not in clean_names:
                clean_names.append(name)
        if config.get("user_manager", "NOI") not in clean_names:
            clean_names.insert(0, config.get("user_manager", "NOI"))
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('config',?)", (json.dumps(config),))
            db.execute("DELETE FROM managers")
            db.executemany("INSERT INTO managers(name,initial_budget,position) VALUES(?,?,?)",
                           [(name, int(config["initial_budget"]), i) for i, name in enumerate(clean_names)])

    def update_league_settings(self, config: dict, participants: int):
        participants = int(participants)
        current_managers = self.managers()
        purchases = self.purchases()
        user = config.get("user_manager", "NOI")
        if participants < 2:
            raise ValueError("Servono almeno due partecipanti.")
        names = [m["name"] for m in current_managers]
        if participants < len(names):
            removable = [name for name in reversed(names) if name != user and
                         not any(p["manager"] == name for p in purchases)]
            needed = len(names) - participants
            if len(removable) < needed:
                raise ValueError("Non puoi rimuovere partecipanti che hanno già acquistato giocatori.")
            for name in removable[:needed]:
                names.remove(name)
        while len(names) < participants:
            number = 1
            candidate = f"Avversario {number}"
            while candidate in names:
                number += 1
                candidate = f"Avversario {number}"
            names.append(candidate)
        roster = {r: int(v) for r, v in config.get("roster", {}).items()}
        minimum_price = int(config.get("minimum_price", 1))
        initial_budget = int(config["initial_budget"])
        for manager in names:
            owned = [p for p in purchases if p["manager"] == manager]
            spent = sum(int(p["price"]) for p in owned)
            for role, slots in roster.items():
                if sum(p["role"] == role for p in owned) > slots:
                    raise ValueError(f"{manager} ha già troppi giocatori nel reparto {role}.")
            remaining_slots = sum(roster.values()) - len(owned)
            if initial_budget - spent < remaining_slots * minimum_price:
                raise ValueError(f"Con queste regole {manager} non avrebbe crediti sufficienti per completare la rosa.")
        config = dict(config)
        config["participants"] = len(names)
        config["minimum_price"] = minimum_price
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('config',?)",
                       (json.dumps(config),))
            for position, name in enumerate(names):
                db.execute("INSERT OR IGNORE INTO managers(name,initial_budget,position) VALUES(?,?,?)",
                           (name, initial_budget, position))
                db.execute("UPDATE managers SET initial_budget=?, position=? WHERE name=?",
                           (initial_budget, position, name))
            placeholders = ",".join("?" for _ in names)
            db.execute(f"DELETE FROM managers WHERE name NOT IN ({placeholders})", names)

    def managers(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("""
                SELECT m.name, m.initial_budget,
                    m.initial_budget-COALESCE(SUM(p.price),0) AS budget_left,
                    COUNT(p.id) AS players_bought
                FROM managers m LEFT JOIN purchases p ON p.manager=m.name
                GROUP BY m.name ORDER BY m.position
            """).fetchall()
        return [dict(r) for r in rows]

    def purchases(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM purchases ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def record_purchase(self, player_id: str, player_name: str, role: str, manager: str,
                        price: int, baseline_fair: float):
        minimum_price = int((self.get_config() or {}).get("minimum_price", 1))
        if int(price) < minimum_price:
            raise ValueError(f"Il prezzo deve essere almeno {minimum_price}.")
        budgets = {m["name"]: m["budget_left"] for m in self.managers()}
        if manager not in budgets:
            raise ValueError("Partecipante non valido.")
        if price > budgets[manager]:
            raise ValueError(f"{manager} ha solo {budgets[manager]} crediti.")
        config = self.get_config() or {}
        roster = config.get("roster", {})
        existing = [p for p in self.purchases() if p["manager"] == manager]
        if sum(1 for p in existing if p["role"] == role) >= int(roster.get(role, 99)):
            raise ValueError(f"Il reparto {role} di {manager} è già completo.")
        if manager == config.get("user_manager", "NOI"):
            other_slots = max(sum(int(v) for v in roster.values()) - len(existing) - 1, 0)
            safe_max = budgets[manager] - other_slots * minimum_price
            if price > safe_max:
                raise ValueError(f"Per completare la rosa, il massimo spendibile ora è {safe_max}.")
        with self.connect() as db:
            try:
                db.execute("""INSERT INTO purchases
                    (player_id,player_name,role,manager,price,baseline_fair,created_at)
                    VALUES(?,?,?,?,?,?,?)""",
                    (player_id, player_name, role, manager, int(price), float(baseline_fair),
                     datetime.now(timezone.utc).isoformat()))
            except sqlite3.IntegrityError as exc:
                raise ValueError("Questo giocatore è già stato acquistato.") from exc

    def undo_last(self) -> Optional[dict]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM purchases ORDER BY id DESC LIMIT 1").fetchone()
            if not row:
                return None
            db.execute("DELETE FROM purchases WHERE id=?", (row["id"],))
        return dict(row)

    def rename_manager(self, old_name: str, new_name: str):
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("Inserisci un nome.")
        if old_name == (self.get_config() or {}).get("user_manager", "NOI"):
            raise ValueError("Il nome della tua squadra resta NOI.")
        with self.connect() as db:
            if db.execute("SELECT 1 FROM managers WHERE name=?", (new_name,)).fetchone():
                raise ValueError("Questo nome esiste già.")
            db.execute("UPDATE managers SET name=? WHERE name=?", (new_name, old_name))
            db.execute("UPDATE purchases SET manager=? WHERE manager=?", (new_name, old_name))

    def set_user_manager(self, manager: str):
        names = {m["name"] for m in self.managers()}
        if manager not in names:
            raise ValueError("Partecipante non valido.")
        config = self.get_config()
        if not config:
            raise ValueError("Asta non configurata.")
        config["user_manager"] = manager
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('config',?)",
                       (json.dumps(config),))

    def reset(self):
        with self.connect() as db:
            db.execute("DELETE FROM purchases")
            db.execute("DELETE FROM managers")
            db.execute("DELETE FROM settings")
