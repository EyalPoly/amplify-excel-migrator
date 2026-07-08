"""Rank existing entity names by string similarity to a bad value, so a foreign-key
failure can be mapped to the closest real record instead of a placeholder."""

from difflib import SequenceMatcher
from typing import Iterable, List, Tuple


def closest(value: object, candidates: Iterable[object], k: int = 5, cutoff: float = 0.4) -> List[Tuple[str, float]]:
    target = str(value).lower()
    scored: List[Tuple[str, float]] = []
    for candidate in candidates:
        name = str(candidate)
        score = SequenceMatcher(None, target, name.lower()).ratio()
        if score >= cutoff:
            scored.append((name, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:k]
