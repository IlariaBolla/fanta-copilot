import os

from streamlit.testing.v1 import AppTest


def test_app_renders_offline_with_bundled_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("FANTA_DB_PATH", str(tmp_path / "smoke.db"))
    monkeypatch.setenv("FANTA_APP_PIN", "xxxxx")
    app = AppTest.from_file("streamlit_app.py", default_timeout=15).run()
    assert not app.exception
    assert app.title[0].value == "⚽ Fanta Auction Copilot"
    app.text_input(key="access_pin").input("xxxxx")
    app.button[0].click().run()
    assert not app.exception
    assert app.title[0].value == "⚽ Prepara la tua asta"


def test_wrong_pin_does_not_open_the_app(tmp_path, monkeypatch):
    monkeypatch.setenv("FANTA_DB_PATH", str(tmp_path / "wrong-pin.db"))
    monkeypatch.setenv("FANTA_APP_PIN", "xxxxx")
    app = AppTest.from_file("streamlit_app.py", default_timeout=15).run()
    app.text_input(key="access_pin").input("sbagliato")
    app.button[0].click().run()
    assert not app.exception
    assert app.title[0].value == "⚽ Fanta Auction Copilot"
    assert any("PIN non corretto" in error.value for error in app.error)


def test_lautaro_alias_is_searchable():
    from src.data_repository import load_players
    from streamlit_app import search_candidates
    result = search_candidates(load_players(), set(), "lau")
    assert result.iloc[0]["name"] == "Martinez L."
    precise = search_candidates(load_players(), set(), "lautar")
    assert precise["name"].tolist() == ["Martinez L."]


def test_bundled_snapshot_contains_current_form():
    from src.data_repository import load_players
    players = load_players()
    assert (players["appearances"] > 0).any()
    assert (players["fantasy_average"] > 0).any()
