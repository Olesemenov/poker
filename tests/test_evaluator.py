import unittest

from poker.cards import Card
from poker.evaluator import best_hand, hand_name, score5


def hand(s: str):
    return [Card.from_str(x) for x in s.split()]


class EvaluatorTest(unittest.TestCase):
    def test_category_order(self):
        hands = [
            "2c 7d 9h Js Kc",  # high card
            "2c 2d 9h Js Kc",  # pair
            "2c 2d 9h 9s Kc",  # two pair
            "2c 2d 2h Js Kc",  # trips
            "5c 6d 7h 8s 9c",  # straight
            "2c 7c 9c Jc Kc",  # flush
            "2c 2d 2h Js Jc",  # full house
            "2c 2d 2h 2s Kc",  # quads
            "5c 6c 7c 8c 9c",  # straight flush
        ]
        scores = [score5(hand(h)) for h in hands]
        self.assertEqual(scores, sorted(scores))
        self.assertEqual(len(set(s[0] for s in scores)), 9)

    def test_wheel_is_lowest_straight(self):
        wheel = score5(hand("Ac 2d 3h 4s 5c"))
        six_high = score5(hand("2c 3d 4h 5s 6c"))
        self.assertEqual(wheel, (4, 5))
        self.assertLess(wheel, six_high)

    def test_kickers(self):
        self.assertGreater(score5(hand("Ac Ad Kh 3s 2c")), score5(hand("Ac Ad Qh 3s 2c")))

    def test_best_of_seven(self):
        score = best_hand(hand("Ac Kc Qc Jc 2d 3h Tc"))
        self.assertEqual(hand_name(score), "Straight flush")
        self.assertEqual(score, (8, 14))

    def test_board_plays_tie(self):
        board = "Ac Kd Qh Js Tc"
        a = best_hand(hand(board) + hand("2c 3d"))
        b = best_hand(hand(board) + hand("4c 5d"))
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
