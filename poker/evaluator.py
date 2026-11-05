"""Hand evaluation. A score is a tuple; bigger tuple = better hand."""
from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Iterable

from .cards import Card

HAND_NAMES = [
    "High card",
    "Pair",
    "Two pair",
    "Three of a kind",
    "Straight",
    "Flush",
    "Full house",
    "Four of a kind",
    "Straight flush",
]


def score5(cards: Iterable[Card]) -> tuple:
    cards = list(cards)
    ranks = sorted((c.rank for c in cards), reverse=True)
    flush = len({c.suit for c in cards}) == 1
    uniq = sorted(set(ranks), reverse=True)

    straight_high = None
    if len(uniq) == 5:
        if uniq[0] - uniq[4] == 4:
            straight_high = uniq[0]
        elif uniq == [14, 5, 4, 3, 2]:  # wheel
            straight_high = 5

    groups = sorted(Counter(ranks).items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    shape = [n for _, n in groups]
    ordered = [r for r, _ in groups]

    if straight_high and flush:
        return (8, straight_high)
    if shape == [4, 1]:
        return (7, *ordered)
    if shape == [3, 2]:
        return (6, *ordered)
    if flush:
        return (5, *ranks)
    if straight_high:
        return (4, straight_high)
    if shape == [3, 1, 1]:
        return (3, *ordered)
    if shape == [2, 2, 1]:
        return (2, *ordered)
    if shape == [2, 1, 1, 1]:
        return (1, *ordered)
    return (0, *ranks)


def best_hand(cards: Iterable[Card]) -> tuple:
    """Best 5-card score out of 5..7 cards."""
    cards = list(cards)
    return max(score5(combo) for combo in combinations(cards, 5))


def hand_name(score: tuple) -> str:
    return HAND_NAMES[score[0]]
