import random
import sys
import unittest


sys.path.insert(0, r"C:\Users\frvyoung16\Desktop\projects\bot1\src")

from commands.economy.minigames import (  # noqa: E402
    MATH_REWARD_MULTIPLIERS,
    MATH_TIMEOUTS,
    generate_math_task,
    generate_math_task_for_difficulty,
    pick_math_difficulty,
)


class MathTaskGenerationTests(unittest.TestCase):
    def test_easy_math_task_uses_easy_contract(self) -> None:
        task = generate_math_task_for_difficulty("easy", random.Random(1))

        self.assertEqual(task.difficulty, "easy")
        self.assertEqual(task.timeout, MATH_TIMEOUTS["easy"])
        self.assertEqual(task.reward_mult, MATH_REWARD_MULTIPLIERS["easy"])
        self.assertIn("=", task.question)
        self.assertIsInstance(task.answer, int)

    def test_medium_math_task_uses_medium_contract(self) -> None:
        task = generate_math_task_for_difficulty("medium", random.Random(2))

        self.assertEqual(task.difficulty, "medium")
        self.assertEqual(task.timeout, MATH_TIMEOUTS["medium"])
        self.assertEqual(task.reward_mult, MATH_REWARD_MULTIPLIERS["medium"])
        self.assertIsInstance(task.answer, int)

    def test_hard_math_task_uses_hard_contract(self) -> None:
        task = generate_math_task_for_difficulty("hard", random.Random(3))

        self.assertEqual(task.difficulty, "hard")
        self.assertEqual(task.timeout, MATH_TIMEOUTS["hard"])
        self.assertEqual(task.reward_mult, MATH_REWARD_MULTIPLIERS["hard"])
        self.assertIsInstance(task.answer, int)

    def test_invalid_difficulty_falls_back_to_easy(self) -> None:
        task = generate_math_task_for_difficulty("weird", random.Random(4))

        self.assertEqual(task.difficulty, "easy")


class MathProfilePolicyTests(unittest.TestCase):
    def test_simple_work_profile_never_generates_hard(self) -> None:
        rng = random.Random(10)
        difficulties = {pick_math_difficulty("simple_work", rng) for _ in range(50)}

        self.assertTrue(difficulties.issubset({"easy", "medium"}))
        self.assertNotIn("hard", difficulties)

    def test_crime_profile_never_generates_easy(self) -> None:
        rng = random.Random(20)
        difficulties = {pick_math_difficulty("crime", rng) for _ in range(50)}

        self.assertTrue(difficulties.issubset({"medium", "hard"}))
        self.assertNotIn("easy", difficulties)

    def test_generate_math_task_uses_profile_policy(self) -> None:
        task = generate_math_task("complex_work", random.Random(30))

        self.assertIn(task.difficulty, {"easy", "medium", "hard"})
        self.assertEqual(task.timeout, MATH_TIMEOUTS[task.difficulty])
        self.assertEqual(task.reward_mult, MATH_REWARD_MULTIPLIERS[task.difficulty])


if __name__ == "__main__":
    unittest.main()
