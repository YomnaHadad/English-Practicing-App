"""Sanity check of the placement-test scoring with simulated learners.

A learner of true level T answers questions at or below T correctly 90% of the
time, the next level up 40% of the time, and anything harder by guessing (25%).
This checks the scoring rule behaves sensibly; it does NOT validate the test
against real learners.
"""
import random

from backend import assessment

LEVELS = assessment.LEVELS


def simulate(true_level: str, rng: random.Random) -> str:
    t = LEVELS.index(true_level)
    answers = {}
    for q in assessment.QUESTIONS:
        gap = LEVELS.index(q["level"]) - t
        p = 0.9 if gap <= 0 else 0.4 if gap == 1 else 0.25
        answers[q["id"]] = q["answer"] if rng.random() < p else (q["answer"] + 1) % len(q["options"])
    return assessment.score(answers)["cefr_level"]


def test_estimates_are_close_to_true_level():
    rng = random.Random(0)
    runs = 300
    within_one = exact = total = 0
    for true in LEVELS:
        for _ in range(runs):
            err = abs(LEVELS.index(simulate(true, rng)) - LEVELS.index(true))
            total += 1
            exact += err == 0
            within_one += err <= 1
    print(f"exact {exact / total:.0%}, within one level {within_one / total:.0%}")
    assert within_one / total >= 0.85


def test_higher_true_level_gives_higher_average_estimate():
    rng = random.Random(1)
    means = [sum(LEVELS.index(simulate(t, rng)) for _ in range(200)) / 200 for t in LEVELS]
    assert means == sorted(means)
