from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from src.auction_engine import AuctionEngine
from src.config import DB_FILE, DEFAULT_ROSTER
from src.data_repository import load_metadata, load_players, snapshot_is_stale
from src.data_refresh import refresh_data
from src.normalization import ALIASES, name_score, normalize_name
from src.persistence import AuctionStore
from src.ui_helpers import ROLE_NAMES, format_timestamp, player_card, team_name


st.set_page_config(page_title="Fanta Auction Copilot 26/27", page_icon="⚽", layout="centered")
st.markdown("""
<style>
  .stApp {background:linear-gradient(180deg,#f5f7fb 0,#fff 330px)}
  [data-testid="stHeader"] {background:transparent}
  .block-container {max-width:760px;padding:1.2rem .9rem 5rem}
  h1 {font-size:2rem!important;letter-spacing:-.035em;margin-bottom:.15rem!important}
  h2,h3 {letter-spacing:-.02em}
  .hero {color:white;border-radius:22px;padding:20px;margin:.7rem 0 1rem;box-shadow:0 12px 28px rgba(15,23,42,.16)}
  .hero.green {background:linear-gradient(135deg,#087f5b,#0aa174)}
  .hero.yellow {background:linear-gradient(135deg,#a16207,#ca8a04)}
  .hero.red {background:linear-gradient(135deg,#b42318,#dc3b2f)}
  .hero h2 {font-size:1.8rem;margin:.25rem 0}.hero h3 {margin:.35rem 0 1rem}
  .hard-stop {font-size:2.7rem;font-weight:900;line-height:1;margin:.4rem 0;letter-spacing:-.04em}
  .metrics {display:flex;gap:10px;margin:.7rem 0 1rem}
  .metric {flex:1;background:#fff;padding:12px;border:1px solid #e6eaf0;border-radius:15px;text-align:center;box-shadow:0 4px 14px rgba(15,23,42,.05)}
  .metric b {font-size:1.3rem;display:block;color:#101828}
  .mini-card {display:flex;justify-content:space-between;align-items:center;gap:12px;padding:13px 14px;background:#fff;border:1px solid #e6eaf0;border-radius:15px;margin:8px 0;box-shadow:0 3px 12px rgba(15,23,42,.04)}
  .stButton button {min-height:48px;border-radius:13px;font-weight:750}
  .stNumberInput button {min-height:42px}
  div[data-baseweb="select"] > div {min-height:50px;border-radius:13px;background:#fff}
  div[data-testid="stMetric"] {background:#fff;padding:10px;border:1px solid #e6eaf0;border-radius:14px;box-shadow:0 3px 12px rgba(15,23,42,.04)}
  button[data-baseweb="tab"] {font-weight:750;font-size:1rem}
  @media(max-width:480px){.block-container{padding-top:.7rem}.hard-stop{font-size:2.45rem}.metric b{font-size:1.1rem}.hero{padding:17px}}
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def cached_players(stamp: float) -> pd.DataFrame:
    return load_players()


@st.cache_resource(ttl=6 * 3600, show_spinner=False)
def automatic_refresh_if_needed():
    if not snapshot_is_stale():
        return {"status": "fresh"}
    try:
        return {"status": "updated", "metadata": refresh_data(include_fbref=True)}
    except Exception as exc:
        return {"status": "fallback", "error": type(exc).__name__}


def get_store() -> AuctionStore:
    custom = os.environ.get("FANTA_DB_PATH")
    return AuctionStore(Path(custom) if custom else DB_FILE)


def setup_screen(store: AuctionStore):
    st.title("⚽ Prepara la tua asta")
    st.write("Bastano queste informazioni. Durante l'asta dovrai solo cercare il giocatore, indicare il prezzo e registrare chi lo compra.")
    with st.form("setup"):
        user_name = st.text_input("Come si chiama la tua squadra?", value="La mia squadra",
                                  help="Questo sarai tu nell'app.", key="setup_user_name")
        participants = st.number_input("Quante squadre partecipano?", 4, 20, 10, 1,
                                       key="setup_participants")
        budget = st.number_input("Quanti crediti ha ogni squadra?", 25, 5000, 500, 50,
                                 key="setup_budget")
        mode_choice = st.radio("Tipo di lega", ["Non lo so", "Classic", "Mantra"],
                               horizontal=True, key="setup_mode")
        if mode_choice == "Non lo so":
            st.caption("Va benissimo: useremo Classic, la modalità più comune.")
        with st.expander("Nomi degli altri partecipanti (facoltativo)"):
            raw_names = st.text_area("Uno per riga", placeholder="Marco\nLuca\nAndrea",
                                     key="setup_names")
            st.caption("Se li lasci vuoti useremo Avversario 1, Avversario 2… Potrai rinominarli dopo.")
        with st.expander("Impostazioni avanzate"):
            cols = st.columns(4)
            roster = {r: cols[i].number_input(r, 0, 30, value, 1, key=f"setup_roster_{r}")
                      for i, (r, value) in enumerate(DEFAULT_ROSTER.items())}
            defense = st.radio("Modificatore difesa", ["Non lo so", "Sì", "No"],
                               horizontal=True, key="setup_defense")
            clean = st.radio("Bonus portiere imbattuto", ["Non lo so", "Sì", "No"],
                             horizontal=True, key="setup_clean")
            minimum_price = st.number_input("Offerta minima per giocatore", 1, 20, 1, 1,
                                            key="setup_minimum_price")
        submitted = st.form_submit_button("INIZIA ASTA", type="primary", width="stretch")
    if submitted:
        user_name = user_name.strip()
        if not user_name:
            st.error("Inserisci il nome della tua squadra.")
            return
        mode = "Classic" if mode_choice == "Non lo so" else mode_choice
        entered = []
        for raw_name in raw_names.splitlines():
            name = raw_name.strip()
            if name and name.casefold() != user_name.casefold() and name not in entered:
                entered.append(name)
        managers = [user_name] + entered[: int(participants) - 1]
        while len(managers) < int(participants):
            candidate = f"Avversario {len(managers)}"
            if candidate not in managers:
                managers.append(candidate)
        config = {"mode": mode, "participants": int(participants), "initial_budget": int(budget),
                  "roster": roster, "defense_modifier": defense, "clean_sheet_bonus": clean,
                  "minimum_price": int(minimum_price), "user_manager": user_name}
        store.save_config(config, managers)
        st.rerun()


def summary(engine: AuctionEngine):
    counts = engine.counts(engine.user)
    bought = sum(counts.values())
    total = sum(engine.config["roster"].values())
    short_names = {"P": "Porta", "D": "Difesa", "C": "Centrocampo", "A": "Attacco"}
    roles = " · ".join(f"{short_names.get(r, r)} {counts.get(r, 0)}/{engine.config['roster'][r]}" for r in engine.config["roster"])
    st.markdown(f"""<div class="metrics"><div class="metric"><small>Crediti</small><b>{engine.budget_left()}</b></div>
    <div class="metric"><small>Rosa</small><b>{bought}/{total}</b></div></div>""", unsafe_allow_html=True)
    st.caption(roles)


def league_summary(config: dict):
    roster = config["roster"]
    composition = "-".join(str(roster.get(r, 0)) for r in ["P", "D", "C", "A"])
    st.caption(f"{config.get('mode', 'Classic')} · {config.get('participants', 10)} squadre · "
               f"{config.get('initial_budget', 500)} crediti · Rosa {composition} · "
               f"Offerta minima {config.get('minimum_price', 1)}")


def search_candidates(players: pd.DataFrame, sold: set[str], query: str) -> pd.DataFrame:
    available = players[~players.player_id.astype(str).isin(sold)].copy()
    query_n = normalize_name(query)
    if not query_n:
        return available.sort_values("fvm_classic", ascending=False).head(30)
    def search_values(row):
        aliases = [alias for alias, target in ALIASES.items() if target == row.normalized_name]
        searchable = " ".join([row.normalized_name] + aliases)
        direct = any(token.startswith(query_n) for token in searchable.split()) or query_n in searchable
        score = (1.0 if direct else
                 max([name_score(query_n, row.normalized_name)] +
                     [name_score(query_n, alias) for alias in aliases]))
        return pd.Series({"direct_match": direct, "search_score": score})
    available[["direct_match", "search_score"]] = available.apply(search_values, axis=1)
    if available.direct_match.any():
        available = available[available.direct_match]
    else:
        threshold = .72 if len(query_n) >= 4 else .64
        available = available[available.search_score >= threshold]
    return available.sort_values(["search_score", "fvm_classic"], ascending=False).head(30)


def live_tab(engine: AuctionEngine, players: pd.DataFrame, store: AuctionStore):
    summary(engine)
    if not engine.purchases:
        st.info("1. Cerca chi viene chiamato  ·  2. Aggiorna il prezzo  ·  3. Registra chi lo compra")
    if engine.purchases and st.button("↩ Ho sbagliato: annulla l'ultimo acquisto", key="undo_last"):
        restored = store.undo_last()
        st.toast(f"Ripristinato: {restored['player_name']}")
        st.rerun()
    version = st.session_state.get("auction_form_version", 0)
    selected = st.session_state.get("selected_player_id")
    role_names = {"P": "Portiere", "D": "Difensore", "C": "Centrocampista", "A": "Attaccante"}
    if selected in engine.sold_ids:
        st.session_state.pop("selected_player_id", None)
        selected = None
    if not selected:
        available = players[~players.player_id.astype(str).isin(engine.sold_ids)].sort_values("name")
        labels = {}
        for _, row in available.iterrows():
            aliases = [alias.title() for alias, target in ALIASES.items()
                       if target == row.normalized_name and len(alias.split()) > 1]
            alias_label = f" ({aliases[0]})" if aliases else ""
            role_label = (str(row.roles_mantra) if engine.config.get("mode") == "Mantra"
                          else role_names.get(str(row.role_classic), str(row.role_classic)))
            labels[str(row.player_id)] = (f"{row['name']}{alias_label} · "
                                           f"{team_name(row.team)} · {role_label}")
        suggestion = st.selectbox(
            "Chi stanno chiamando?",
            available.player_id.astype(str).tolist(),
            index=None,
            placeholder="Apri e scrivi le prime lettere…",
            format_func=lambda player_id: labels.get(str(player_id), str(player_id)),
            key=f"player_picker_{version}",
            help="Dopo aver aperto il menu puoi digitare nome o cognome per filtrare.",
        )
        st.caption("Tocca il menu e digita subito il nome: non serve scorrere l'elenco.")
        if suggestion:
            st.session_state["selected_player_id"] = str(suggestion)
            st.rerun()
        return
    player = players[players.player_id.astype(str) == selected].iloc[0]
    auction_ceiling = max([int(m["budget_left"]) for m in engine.managers] + [1])
    if st.button("← Cambia giocatore", key=f"change_{version}"):
        st.session_state.pop("selected_player_id", None)
        st.session_state["auction_form_version"] = version + 1
        st.rerun()
    minimum_price = int(engine.config.get("minimum_price", 1))
    current = st.number_input("Prezzo adesso", min_value=minimum_price,
                              max_value=max(auction_ceiling, minimum_price), value=minimum_price,
                              step=1, key=f"bid_{version}_{selected}",
                              help="Se viene venduto, questo sarà anche il prezzo finale.")
    rec = engine.recommend(selected, int(current))
    color = "green" if "🟢" in rec.action else "yellow" if "🟡" in rec.action else "red"
    role_label = (player.roles_mantra if engine.config.get("mode") == "Mantra"
                  else role_names.get(str(player.role_classic), str(player.role_classic)))
    st.markdown(f"""<div class="hero {color}"><small>{team_name(player.team)} · {role_label} · FASCIA {rec.tier}</small>
    <h2>{player['name']}</h2><h3>{rec.action}</h3><div>PREZZO CONSIGLIATO: <b>{rec.target_price}</b></div>
    <div class="hard-stop">NON SUPERARE {rec.hard_stop}</div></div>""", unsafe_allow_html=True)
    form_bits = []
    if int(player.get("appearances", 0)):
        form_bits.append(f"{int(player.appearances)} presenze")
    if int(player.get("goals", 0)):
        form_bits.append(f"{int(player.goals)} gol")
    if int(player.get("assists", 0)):
        form_bits.append(f"{int(player.assists)} assist")
    if float(player.get("fantasy_average", 0)):
        form_bits.append(f"fantamedia {float(player.fantasy_average):.2f}")
    if form_bits:
        st.caption("Forma attuale: " + " · ".join(form_bits))
    previous_bits = []
    if int(player.get("previous_appearances", 0)):
        previous_bits.append(f"{int(player.previous_appearances)} presenze")
    if int(player.get("previous_goals", 0)):
        previous_bits.append(f"{int(player.previous_goals)} gol")
    if int(player.get("previous_assists", 0)):
        previous_bits.append(f"{int(player.previous_assists)} assist")
    if float(player.get("previous_fantasy_average", 0)):
        previous_bits.append(f"fantamedia {float(player.previous_fantasy_average):.2f}")
    if previous_bits:
        st.caption("Stagione 2025/26: " + " · ".join(previous_bits))
    for reason in rec.reasons[:3]:
        st.markdown(f"- {reason['text']}")
    impact = engine.purchase_impact(selected, int(current))
    st.markdown(f"""<div class="mini-card"><span><b>Se lo compri adesso</b><br>
    <small>Ti restano {impact['budget_after']} crediti per {impact['remaining_slots']} giocatori ·
    riserva minima {impact['reserve_needed']}</small></span></div>""", unsafe_allow_html=True)
    if impact["role_budget_after"] < 0:
        st.warning(f"Supereresti di {-impact['role_budget_after']} crediti il piano attuale per questo reparto.")
    if impact["rival"] and impact["gap_closed_percent"] > 0:
        st.caption(f"Questo acquisto recupererebbe circa il {impact['gap_closed_percent']}% del divario "
                   f"nel reparto rispetto a {impact['rival']}.")
    if rec.alternatives:
        with st.expander("Se passi: alternative simili"):
            for alt in rec.alternatives:
                st.write(f"{alt.name} — stop {alt.hard_stop}")
    st.divider()
    manager_names = [m["name"] for m in engine.managers]
    no_buyer = "— Non è ancora stato venduto —"
    buyer = st.selectbox("Quando finisce: chi lo ha comprato?", [no_buyer] + manager_names,
                         key=f"buyer_{version}")
    buyer_budget = engine.budget_left(buyer) if buyer != no_buyer else 0
    invalid_budget = buyer != no_buyer and int(current) > buyer_budget
    if invalid_budget:
        st.error(f"{buyer} ha solo {buyer_budget} crediti.")
    label = "SCEGLI CHI LO HA COMPRATO" if buyer == no_buyer else f"REGISTRA: {buyer} A {current} CREDITI"
    if st.button(label, type="primary", width="stretch",
                 disabled=buyer == no_buyer or invalid_budget, key=f"record_{version}"):
        try:
            store.record_purchase(selected, player["name"], player.role_classic, buyer, int(current), engine.baseline_fair(selected))
            st.session_state["auction_form_version"] = version + 1
            st.session_state.pop("selected_player_id", None)
            st.toast(f"{player['name']} → {buyer}, {current} crediti")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def roster_tab(engine: AuctionEngine, players: pd.DataFrame):
    mine = engine.user_purchases()
    spent = sum(p["price"] for p in mine)
    c1, c2, c3 = st.columns(3)
    c1.metric("Spesi", spent); c2.metric("Rimasti", engine.budget_left()); c3.metric("Giocatori", len(mine))
    if mine:
        value_ratio = sum(float(p["baseline_fair"]) for p in mine) / max(spent, 1)
        quality = "Ottima" if value_ratio >= 1.10 else "Buona" if value_ratio >= .85 else "Da migliorare"
    else:
        quality = "Da costruire"
    st.markdown(f"**Qualità degli acquisti: {quality}**")
    budget_plan = engine.remaining_budget_plan()
    if any(engine.config["roster"].get(r, 0) > engine.counts(engine.user).get(r, 0)
           for r in engine.config["roster"]):
        st.subheader("Piano dei crediti rimasti")
        labels = {"P": "Porta", "D": "Difesa", "C": "Centrocampo", "A": "Attacco"}
        rows = st.columns(2)
        for index, role in enumerate(["P", "D", "C", "A"]):
            rows[index % 2].metric(labels[role], f"{budget_plan.get(role, 0)} cr")
        st.caption("Queste riserve si ricalcolano dopo ogni acquisto e sommano al tuo budget residuo.")
    plans = engine.squad_plan()
    if plans:
        st.subheader("Cosa ti serve adesso")
        first = plans[0]
        st.success(f"**Priorità: {first['label']}** — {first['reason']}")
        for plan in plans:
            st.markdown(f"""<div class="mini-card"><span><b>{plan['label']}: {plan['player']}</b><br>
            <small>{plan['reason']}</small></span><strong>STOP {plan['hard_stop']}</strong></div>""",
                        unsafe_allow_html=True)
        st.caption("È un piano dinamico: cambia quando tu o gli avversari acquistate un giocatore.")
    st.subheader("I tuoi acquisti")
    for role, title in ROLE_NAMES.items():
        st.subheader(title)
        rows = [p for p in mine if p["role"] == role]
        if not rows: st.caption("Ancora nessun acquisto")
        for p in rows:
            team_rows = players[players.player_id.astype(str) == str(p["player_id"])]
            team = team_rows.iloc[0].team if not team_rows.empty else ""
            st.markdown(player_card(p["player_name"], team, role, p["price"]), unsafe_allow_html=True)


def opponents_tab(engine: AuctionEngine):
    opponents = [m for m in engine.managers if m["name"] != engine.user]
    if not opponents:
        st.caption("Nessun avversario configurato.")
        return
    for m in opponents:
        counts = engine.counts(m["name"])
        roles = (f"Porta {counts.get('P', 0)} · Difesa {counts.get('D', 0)} · "
                 f"Centrocampo {counts.get('C', 0)} · Attacco {counts.get('A', 0)}")
        st.markdown(f"**{m['name']}** — {m['budget_left']} crediti, {m['players_bought']} acquisti")
        st.caption(roles)


def data_and_reset(store: AuctionStore, metadata: dict):
    with st.expander("Stato dati e opzioni"):
        st.write(f"Dati aggiornati: {format_timestamp(metadata.get('updated_at', ''))}")
        st.caption(f"Stagione {metadata.get('season', '2026/27')} · {metadata.get('players', '?')} giocatori")
        for source, status in metadata.get("health", {}).items(): st.write(f"{source}: {status}")
        if st.button("Aggiorna dati online", width="stretch", key="refresh_data"):
            try:
                with st.spinner("Aggiornamento in corso…"):
                    refresh_data(include_fbref=True)
                cached_players.clear()
                st.success("Dati aggiornati.")
                st.rerun()
            except Exception:
                st.warning("Dati online non raggiungibili: uso ultimo aggiornamento disponibile.")
        opponents = [m["name"] for m in store.managers() if m["name"] != (store.get_config() or {}).get("user_manager", "NOI")]
        if opponents:
            st.markdown("**Rinomina partecipante**")
            old_name = st.selectbox("Partecipante", opponents, key="rename_old")
            new_name = st.text_input("Nuovo nome", key="rename_new")
            if st.button("Salva nome", width="stretch", key="save_manager_name"):
                try:
                    store.rename_manager(old_name, new_name); st.rerun()
                except ValueError as exc: st.error(str(exc))
        export = {"config": store.get_config(), "managers": store.managers(), "purchases": store.purchases()}
        st.download_button("Esporta asta (JSON)", json.dumps(export, ensure_ascii=False, indent=2), "asta.json", "application/json", width="stretch")
        confirm = st.checkbox("Confermo di voler cancellare questa asta", key="confirm_reset")
        if st.button("Nuova asta / Reset", disabled=not confirm, width="stretch", key="reset_auction"):
            store.reset(); st.rerun()


def league_settings(store: AuctionStore, config: dict):
    with st.expander("⚙️ Regole e personalizzazione dell'asta"):
        st.write("Le regole influenzano direttamente prezzi, priorità e crediti da conservare.")
        with st.form("league_settings"):
            mode = st.selectbox("Tipo di lega", ["Classic", "Mantra"],
                                index=1 if config.get("mode") == "Mantra" else 0,
                                key="edit_mode")
            participants = st.number_input("Numero di squadre", 4, 20,
                                           int(config.get("participants", 10)), 1,
                                           key="edit_participants")
            budget = st.number_input("Crediti iniziali per squadra", 25, 5000,
                                     int(config.get("initial_budget", 500)), 25,
                                     key="edit_budget")
            minimum_price = st.number_input("Offerta minima per giocatore", 1, 20,
                                            int(config.get("minimum_price", 1)), 1,
                                            key="edit_minimum_price")
            defense_options = ["Non lo so", "Sì", "No"]
            defense = st.radio("Modificatore difesa", defense_options,
                               index=defense_options.index(config.get("defense_modifier", "Non lo so")),
                               horizontal=True, key="edit_defense")
            clean = st.radio("Bonus portiere imbattuto", defense_options,
                             index=defense_options.index(config.get("clean_sheet_bonus", "Non lo so")),
                             horizontal=True, key="edit_clean")
            st.markdown("**Composizione della rosa**")
            columns = st.columns(4)
            role_labels = {"P": "Portieri", "D": "Difensori", "C": "Centrocampisti", "A": "Attaccanti"}
            roster = {role: columns[index].number_input(role_labels[role], 0, 30,
                                                        int(config["roster"].get(role, 0)), 1,
                                                        key=f"edit_roster_{role}")
                      for index, role in enumerate(["P", "D", "C", "A"])}
            save = st.form_submit_button("SALVA REGOLE", type="primary", width="stretch")
        if save:
            updated = dict(config)
            updated.update({"mode": mode, "participants": int(participants),
                            "initial_budget": int(budget), "minimum_price": int(minimum_price),
                            "defense_modifier": defense, "clean_sheet_bonus": clean,
                            "roster": roster})
            try:
                store.update_league_settings(updated, int(participants))
                st.success("Regole aggiornate: il piano è stato ricalcolato.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


def main():
    store = get_store()
    if not store.is_configured():
        setup_screen(store)
        return
    players_path = Path(__file__).resolve().parent / "data" / "current_players.csv"
    players = cached_players(players_path.stat().st_mtime)
    refresh_status = automatic_refresh_if_needed()
    if refresh_status["status"] == "updated":
        cached_players.clear()
        players = cached_players(players_path.stat().st_mtime)
    elif refresh_status["status"] == "fallback":
        st.warning("Dati online non raggiungibili: uso ultimo aggiornamento disponibile.")
    metadata = load_metadata()
    config = store.get_config()
    st.title("⚽ Assistente asta")
    league_summary(config)
    manager_names = [m["name"] for m in store.managers()]
    current_user = config.get("user_manager", manager_names[0])
    current_index = manager_names.index(current_user) if current_user in manager_names else 0
    identity = st.selectbox("La tua squadra", manager_names, index=current_index,
                            help="Seleziona quale partecipante sei tu.", key="identity_manager")
    if identity != current_user:
        store.set_user_manager(identity)
        st.rerun()
    config = store.get_config()
    engine = AuctionEngine(players, config, store.managers(), store.purchases())
    tabs = st.tabs(["🔥 Asta", "👕 La mia squadra"])
    with tabs[0]: live_tab(engine, players, store)
    with tabs[1]:
        roster_tab(engine, players)
        with st.expander("Situazione degli avversari"):
            opponents_tab(engine)
        league_settings(store, config)
        data_and_reset(store, metadata)
    st.caption(f"Dati aggiornati: {format_timestamp(metadata.get('updated_at', ''))}")


if __name__ == "__main__":
    main()
