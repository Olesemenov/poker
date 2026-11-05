"""No-limit Texas Hold'em table: a pure, UI-agnostic state machine.

Used by the offline UI directly and by the online server. Bet amounts are
"raise to" totals for the current betting round.

Known simplifications (see docs/PLAN.md): no burn cards, a short all-in raise
does not re-open betting, no rake/timers.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Optional

from .cards import Card, Deck
from .evaluator import best_hand, hand_name

MAX_SEATS = 6


class PokerError(Exception):
    """Illegal action or illegal table state."""


@dataclass
class Player:
    id: str
    name: str
    stack: int
    hole: list = field(default_factory=list)
    bet: int = 0  # chips put in during the current betting round
    total: int = 0  # chips put in during the whole hand
    in_hand: bool = False
    folded: bool = False
    all_in: bool = False
    acted: bool = False
    left: bool = False

    @property
    def live(self) -> bool:
        return self.in_hand and not self.folded

    @property
    def can_act(self) -> bool:
        return self.live and not self.all_in


class Table:
    def __init__(
        self,
        small_blind: int = 10,
        big_blind: int = 20,
        rng: Optional[random.Random] = None,
        max_seats: int = MAX_SEATS,
    ):
        self.sb = small_blind
        self.bb = big_blind
        self.rng = rng or random.Random()
        self.max_seats = max_seats
        self.players: list[Player] = []
        self.dealer = -1
        self.phase = "waiting"  # waiting | preflop | flop | turn | river
        self.board: list[Card] = []
        self.deck: Optional[Deck] = None
        self.current: Optional[int] = None
        self.current_bet = 0
        self.min_raise = big_blind
        self.last_result: Optional[dict] = None
        self.hand_no = 0

    # ------------------------------------------------------------ seats
    def add_player(self, pid: str, name: str, stack: int) -> Player:
        if any(p.id == pid for p in self.players):
            raise PokerError("player already seated")
        if len(self.players) >= self.max_seats:
            raise PokerError("table is full")
        if stack <= 0:
            raise PokerError("stack must be positive")
        p = Player(pid, name, stack)
        self.players.append(p)
        return p

    def get(self, pid: str) -> Player:
        for p in self.players:
            if p.id == pid:
                return p
        raise PokerError("unknown player")

    def leave(self, pid: str) -> None:
        p = self.get(pid)
        if self.phase == "waiting":
            i = self.players.index(p)
            self.players.remove(p)
            if i <= self.dealer:
                self.dealer -= 1
            return
        p.left = True  # removed lazily at the next start_hand
        if not p.live:
            return
        if self.current is not None and self.players[self.current] is p:
            self.act(pid, "fold")
            return
        p.folded = True
        live = [q for q in self.players if q.live]
        if len(live) == 1:
            self._award_uncontested(live[0])
        elif self._round_complete():
            self._next_street()

    # ------------------------------------------------------------ helpers
    def _next_index(self, start: int, pred: Callable[[Player], bool]) -> Optional[int]:
        n = len(self.players)
        for k in range(1, n + 1):
            i = (start + k) % n
            if pred(self.players[i]):
                return i
        return None

    def _post(self, p: Player, amount: int) -> None:
        amount = min(amount, p.stack)
        p.stack -= amount
        p.bet += amount
        p.total += amount
        if p.stack == 0:
            p.all_in = True

    @property
    def pot(self) -> int:
        return sum(p.total for p in self.players)

    def _round_complete(self) -> bool:
        return all(p.acted and p.bet == self.current_bet for p in self.players if p.can_act)

    # ------------------------------------------------------------ hand flow
    def start_hand(self) -> None:
        if self.phase != "waiting":
            raise PokerError("hand already in progress")
        if self.dealer >= 0 and self.dealer < len(self.players):
            dealer_id = self.players[self.dealer].id
        else:
            dealer_id = None
        self.players = [p for p in self.players if not p.left]
        if dealer_id is not None:
            idx = [i for i, p in enumerate(self.players) if p.id == dealer_id]
            self.dealer = idx[0] if idx else self.dealer - 1
        if len([p for p in self.players if p.stack > 0]) < 2:
            raise PokerError("need at least 2 players with chips")

        for p in self.players:
            p.hole, p.bet, p.total = [], 0, 0
            p.folded = p.all_in = p.acted = False
            p.in_hand = p.stack > 0
        self.deck = Deck(self.rng)
        self.board = []
        self.last_result = None
        self.hand_no += 1

        in_hand = lambda p: p.in_hand  # noqa: E731
        self.dealer = self._next_index(self.dealer, in_hand)
        if len([p for p in self.players if p.in_hand]) == 2:  # heads-up
            sb_i = self.dealer
        else:
            sb_i = self._next_index(self.dealer, in_hand)
        bb_i = self._next_index(sb_i, in_hand)
        self._post(self.players[sb_i], self.sb)
        self._post(self.players[bb_i], self.bb)

        for _ in range(2):
            i = sb_i
            for _ in range(len([p for p in self.players if p.in_hand])):
                self.players[i].hole.append(self.deck.draw())
                i = self._next_index(i, in_hand)

        self.phase = "preflop"
        self.current_bet = max(p.bet for p in self.players)
        self.min_raise = self.bb
        can = [p for p in self.players if p.can_act]
        if len(can) == 0 or (len(can) == 1 and can[0].bet >= self.current_bet):
            self._next_street()
        else:
            self.current = self._next_index(bb_i, lambda p: p.can_act)

    def legal_actions(self, pid: str) -> dict:
        if self.phase == "waiting" or self.current is None:
            return {}
        p = self.players[self.current]
        if p.id != pid:
            return {}
        to_call = self.current_bet - p.bet
        maxto = p.bet + p.stack
        raise_info = None
        if p.stack > to_call:
            raise_info = {"min": min(self.current_bet + self.min_raise, maxto), "max": maxto}
        return {
            "fold": True,
            "check": to_call == 0,
            "call": min(to_call, p.stack) if to_call > 0 else 0,
            "raise": raise_info,
        }

    def act(self, pid: str, action: str, amount: int = 0) -> None:
        if self.phase == "waiting" or self.current is None:
            raise PokerError("no hand in progress")
        p = self.players[self.current]
        if p.id != pid:
            raise PokerError("not your turn")
        to_call = self.current_bet - p.bet

        if action == "fold":
            p.folded = True
        elif action == "check":
            if to_call > 0:
                raise PokerError("cannot check, you must call or fold")
        elif action == "call":
            if to_call <= 0:
                raise PokerError("nothing to call, use check")
            self._post(p, to_call)
        elif action in ("raise", "bet", "allin"):
            maxto = p.bet + p.stack
            to = maxto if action == "allin" else int(amount)
            if to > maxto:
                raise PokerError("not enough chips")
            if to <= self.current_bet:
                if action == "allin":
                    self._post(p, p.stack)  # all-in for a call or less
                else:
                    raise PokerError("raise must exceed the current bet")
            else:
                min_to = self.current_bet + self.min_raise
                if to < min_to and to != maxto:
                    raise PokerError(f"minimum raise is to {min_to}")
                size = to - self.current_bet
                self._post(p, to - p.bet)
                if size >= self.min_raise:
                    self.min_raise = size
                    for q in self.players:
                        if q is not p and q.can_act:
                            q.acted = False
                self.current_bet = to
        else:
            raise PokerError(f"unknown action {action!r}")

        p.acted = True
        self._after_action()

    def _after_action(self) -> None:
        live = [p for p in self.players if p.live]
        if len(live) == 1:
            self._award_uncontested(live[0])
        elif self._round_complete():
            self._next_street()
        else:
            self.current = self._next_index(self.current, lambda p: p.can_act)

    def _next_street(self) -> None:
        while True:
            for p in self.players:
                p.bet = 0
                p.acted = False
            self.current_bet = 0
            self.min_raise = self.bb
            if self.phase == "preflop":
                self.phase = "flop"
                self.board += [self.deck.draw() for _ in range(3)]
            elif self.phase == "flop":
                self.phase = "turn"
                self.board.append(self.deck.draw())
            elif self.phase == "turn":
                self.phase = "river"
                self.board.append(self.deck.draw())
            else:
                self._showdown()
                return
            if len([p for p in self.players if p.can_act]) >= 2:
                self.current = self._next_index(self.dealer, lambda p: p.can_act)
                return

    # ------------------------------------------------------------ results
    def _end_hand(self) -> None:
        self.phase = "waiting"
        self.current = None
        for p in self.players:
            p.bet = 0

    def _award_uncontested(self, winner: Player) -> None:
        amount = self.pot
        winner.stack += amount
        self.last_result = {
            "showdown": False,
            "winners": [{"id": winner.id, "amount": amount, "hand": None}],
            "pots": [{"amount": amount, "winners": [winner.id]}],
        }
        self._end_hand()

    def _showdown(self) -> None:
        n = len(self.players)
        live = [p for p in self.players if p.live]
        scores = {p.id: best_hand(p.hole + self.board) for p in live}
        levels = sorted({p.total for p in self.players if p.total > 0})
        payouts: dict[str, int] = {}
        pots = []
        prev = 0
        for lvl in levels:
            amount = sum(min(p.total, lvl) - min(p.total, prev) for p in self.players)
            prev = lvl
            elig = [p for p in live if p.total >= lvl] or live
            best = max(scores[p.id] for p in elig)
            winners = [p for p in elig if scores[p.id] == best]
            winners.sort(key=lambda p: (self.players.index(p) - self.dealer - 1) % n)
            share, rem = divmod(amount, len(winners))
            for i, w in enumerate(winners):
                payouts[w.id] = payouts.get(w.id, 0) + share + (1 if i < rem else 0)
            pots.append({"amount": amount, "winners": [w.id for w in winners]})
        for p in self.players:
            p.stack += payouts.get(p.id, 0)
        self.last_result = {
            "showdown": True,
            "winners": [
                {"id": pid, "amount": amt, "hand": hand_name(scores[pid])}
                for pid, amt in payouts.items()
            ],
            "pots": pots,
        }
        self._end_hand()

    # ------------------------------------------------------------ view
    def public_state(self, viewer: Optional[str] = None) -> dict:
        reveal = bool(self.last_result and self.last_result["showdown"]) and self.phase == "waiting"
        players = []
        for i, p in enumerate(self.players):
            if viewer == p.id or (reveal and p.live):
                cards = [str(c) for c in p.hole]
            else:
                cards = ["??"] * len(p.hole)
            players.append(
                {
                    "id": p.id,
                    "name": p.name,
                    "stack": p.stack,
                    "bet": p.bet,
                    "folded": p.folded,
                    "all_in": p.all_in,
                    "in_hand": p.in_hand,
                    "is_dealer": i == self.dealer,
                    "is_current": i == self.current,
                    "cards": cards,
                }
            )
        return {
            "hand_no": self.hand_no,
            "phase": self.phase,
            "board": [str(c) for c in self.board],
            "pot": self.pot,
            "current_bet": self.current_bet,
            "players": players,
            "you": viewer,
            "legal": self.legal_actions(viewer) if viewer else {},
            "result": self.last_result,
            "blinds": [self.sb, self.bb],
        }
