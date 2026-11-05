import random
import unittest

from poker.game import PokerError, Table


def make_table(stacks, seed=1, sb=5, bb=10):
    t = Table(sb, bb, rng=random.Random(seed))
    for i, s in enumerate(stacks):
        t.add_player(f"p{i}", f"P{i}", s)
    return t


class TableTest(unittest.TestCase):
    def test_needs_two_players(self):
        t = make_table([100])
        with self.assertRaises(PokerError):
            t.start_hand()

    def test_max_six_seats(self):
        t = make_table([100] * 6)
        with self.assertRaises(PokerError):
            t.add_player("x", "X", 100)

    def test_blinds_and_first_to_act_three_handed(self):
        t = make_table([100, 100, 100])
        t.start_hand()
        # dealer p0, sb p1, bb p2, first to act p0
        self.assertEqual(t.players[t.dealer].id, "p0")
        self.assertEqual(t.players[1].bet, 5)
        self.assertEqual(t.players[2].bet, 10)
        self.assertEqual(t.players[t.current].id, "p0")

    def test_heads_up_dealer_is_small_blind_and_acts_first(self):
        t = make_table([100, 100])
        t.start_hand()
        d = t.players[t.dealer]
        self.assertEqual(d.bet, 5)
        self.assertIs(t.players[t.current], d)

    def test_fold_wins_pot(self):
        t = make_table([100, 100])
        t.start_hand()
        t.act(t.players[t.current].id, "fold")
        self.assertEqual(t.phase, "waiting")
        self.assertEqual(sorted(p.stack for p in t.players), [95, 105])
        self.assertFalse(t.last_result["showdown"])

    def test_wrong_turn_and_illegal_check(self):
        t = make_table([100, 100, 100])
        t.start_hand()
        with self.assertRaises(PokerError):
            t.act("p1", "call")
        with self.assertRaises(PokerError):
            t.act("p0", "check")  # facing the big blind
        with self.assertRaises(PokerError):
            t.act("p0", "raise", 12)  # below minimum raise (to 20)

    def test_hidden_cards(self):
        t = make_table([100, 100])
        t.start_hand()
        st = t.public_state("p0")
        other = [p for p in st["players"] if p["id"] == "p1"][0]
        mine = [p for p in st["players"] if p["id"] == "p0"][0]
        self.assertEqual(other["cards"], ["??", "??"])
        self.assertNotIn("??", mine["cards"])

    def test_side_pots_conserve_chips_and_cap_losses(self):
        for seed in range(30):
            t = make_table([50, 200, 400], seed=seed)
            t.start_hand()
            while t.phase != "waiting":
                t.act(t.players[t.current].id, "allin")
            self.assertEqual(sum(p.stack for p in t.players), 650)
            self.assertEqual(sum(p["amount"] for p in t.last_result["pots"]), 650)


class RandomPlayTest(unittest.TestCase):
    def play(self, seed, n):
        rng = random.Random(seed)
        t = make_table([rng.choice([50, 100, 300, 1000]) for _ in range(n)], seed=seed)
        total = sum(p.stack for p in t.players)
        for _ in range(40):
            try:
                t.start_hand()
            except PokerError:
                break
            steps = 0
            while t.phase != "waiting":
                p = t.players[t.current]
                la = t.legal_actions(p.id)
                options = ["fold", "allin"]
                if la["check"]:
                    options += ["check"] * 4
                if la["call"]:
                    options += ["call"] * 4
                if la["raise"]:
                    options += ["raise"] * 2
                choice = rng.choice(options)
                if choice == "raise":
                    t.act(p.id, "raise", rng.randint(la["raise"]["min"], la["raise"]["max"]))
                else:
                    t.act(p.id, choice)
                steps += 1
                self.assertLess(steps, 200)
            self.assertEqual(sum(p.stack for p in t.players), total)
            self.assertTrue(all(p.stack >= 0 for p in t.players))

    def test_random_games(self):
        for seed in range(200):
            self.play(seed, 2 + seed % 5)


if __name__ == "__main__":
    unittest.main()
