from src.normalization import best_unambiguous_match, normalize_name


def test_accents_punctuation_and_aliases():
    assert normalize_name("Højlund") == "hojlund"
    assert normalize_name("Lautaro Martínez") == "martinez l"
    assert normalize_name("  D'Amico  ") == "d amico"


def test_ambiguous_match_is_not_silent():
    assert best_unambiguous_match("Rossi", ["Rossi A.", "Rossi M."]) is None
