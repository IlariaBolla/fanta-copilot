# DEPLOY IN 5 MINUTES

1. Push this repository to GitHub.
2. Open [Streamlit Community Cloud](https://share.streamlit.io/).
3. Create an app from this repository.
4. Set the entrypoint to `fanta-copilot/streamlit_app.py`.
5. In Advanced settings, add `APP_PIN = "your-private-pin"` to Streamlit Secrets.
6. Send your friend the Streamlit link and the PIN through a private channel.

No API key, database, upload, or terminal is required by the final user. The owner configures one access PIN in Streamlit Secrets.

# Fanta Auction Copilot 2026/27

Mobile-first auction assistant for Italian Fantacalcio. The user explicitly chooses which auction participant they are. The live flow is deliberately short: search the player, update one price, read the stop, choose the buyer, and register. The app records every sale in SQLite and recalculates value, current form, scarcity, market level, opponent strength by role, roster need, alternatives, and a budget-safe hard stop after every purchase.

## Owner notes

The app is designed for one active auction. Streamlit Community Cloud local files can be replaced when an app sleeps, reboots, or redeploys, so the advanced section includes a JSON export as an optional safety copy. Normal auction use requires no export.

The live recommendation path never accesses the network. The bundled snapshot keeps the app usable if Fantacalcio.it or FBref is unavailable. Source health and the last update time are visible under “Stato dati e opzioni”. Missing enrichment values are left empty/zero and are never invented.

When the snapshot is older than six hours, the app performs one cached best-effort refresh. A manual refresh button is also available in the data-status section. Both paths retain the existing snapshot if a source fails.

## Developer setup

Python 3.11 or newer is recommended.

```bash
python -m pip install -r requirements.txt
python scripts/refresh_data.py
pytest -q
streamlit run streamlit_app.py
```

The refresh makes one request to the public Fantacalcio quotation page and, optionally, one to the public FBref standard-statistics page. It uses timeouts and a descriptive User-Agent. A failed refresh does not delete the bundled last-known-good files.

## Data and architecture

- `data/current_players.csv`: deployable last-known-good 2026/27 snapshot.
- `data/metadata.json`: timestamp, source health, and matching report.
- `src/data_sources.py`: public parsers and conservative name matching.
- `src/auction_engine.py`: deterministic recommendations and invariants.
- `src/persistence.py`: zero-configuration SQLite auction state.
- `scripts/refresh_data.py`: manual/deployment-time refresh utility.

Fantacalcio.it is authoritative for current clubs, roles, quotations, FVM, and current-season performance. The 2025/26 Fantacalcio statistics are a secondary, capped signal when a current player has enough historical appearances; they never replace the current 2026/27 list or dominate FVM. FBref is optional and only supplies limited current-season performance context when accessible.

Run `python scripts/simulate_auction.py` for a deterministic 250-purchase auction with imaginary players. It verifies complete rosters, non-negative budgets, no duplicate sales, solvency-safe hard stops, opponent reaction, market inflation/deflation, and use of the historical signal.
