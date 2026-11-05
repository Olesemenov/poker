"""Cards and deck."""
from __future__ import annotations

import random
from dataclasses import dataclass

RANKS = "23456789TJQKA"  # rank value = index + 2
SUITS = "cdhs"


@dataclass(frozen=True)
class Card:
    rank: int  # 2..14 (14 = ace)
    suit: str  # one of SUITS

    def __str__(self) -> str:
        return RANKS[self.rank - 2] + self.suit

    @classmethod
    def from_str(cls, s: str) -> "Card":
        return cls(RANKS.index(s[0].upper()) + 2, s[1].lower())


class Deck:
    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self.cards = [Card(r, s) for r in range(2, 15) for s in SUITS]
        self.rng.shuffle(self.cards)

    def draw(self) -> Card:
        return self.cards.pop()
