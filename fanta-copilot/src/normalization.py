import re
import unicodedata
from difflib import SequenceMatcher

ALIASES = {
    "lautaro martinez": "martinez l",
    "l martinez": "martinez l",
    "hakan calhanoglu": "calhanoglu",
    "nicolo barella": "barella",
    "nicolas paz": "paz n",
}


def normalize_name(value: str) -> str:
    value = str(value or "").translate(str.maketrans({"ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "đ": "d"}))
    text = unicodedata.normalize("NFKD", value)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = text.replace("’", "'").replace("`", "'")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return ALIASES.get(text, text)


def name_score(left: str, right: str) -> float:
    a, b = normalize_name(left), normalize_name(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.93
    return SequenceMatcher(None, a, b).ratio()


def best_unambiguous_match(name: str, candidates: list[str], threshold: float = 0.88):
    ranked = sorted(((name_score(name, c), c) for c in candidates), reverse=True)
    if not ranked or ranked[0][0] < threshold:
        return None
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 0.035:
        return None
    return ranked[0][1]
