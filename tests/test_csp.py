"""Tests for Solution A. Run from the repo root: python3 -m unittest discover tests -v"""
from __future__ import annotations

import json
import random
import unittest
from pathlib import Path

import ttdp_tool
from solvers.csp import solve, to_hhmm

ROOT = Path(__file__).resolve().parent.parent


def make_instance(pois: list[dict], travel: dict[str, dict[str, int]], day: tuple[str, str]) -> dict:
    """A minimal instance; each POI is {id, window, duration, must}."""
    return {
        "day_window": {"start": day[0], "end": day[1]},
        "start_location": "H",
        "return_to_start": True,
        "pois": [
            {"id": p["id"], "opening_windows": [list(p["window"])], "visit_duration": p["duration"],
             "must_visit": p.get("must", True), "entry_fee": 0}
            for p in pois
        ],
        "travel_times": travel,
    }


def random_instance(rng: random.Random) -> dict:
    """Travel times are 5 x Manhattan distance on a grid, so the triangle inequality holds."""
    ids = [f"P{k}" for k in range(rng.randint(2, 7))]
    coords = {x: (rng.randint(0, 6), rng.randint(0, 6)) for x in ["H", *ids]}
    travel = {
        a: {b: 5 * (abs(ax - bx) + abs(ay - by)) for b, (bx, by) in coords.items() if b != a}
        for a, (ax, ay) in coords.items()
    }
    pois = []
    for k, x in enumerate(ids):
        opens = rng.randrange(8 * 60, 14 * 60, 15)
        pois.append({
            "id": x,
            "window": (to_hhmm(opens), to_hhmm(opens + rng.randrange(60, 8 * 60, 15))),
            "duration": rng.choice([15, 30, 45, 60, 90]),
            # At least one must-visit: ttdp_tool cannot handle a plan with no stops.
            "must": k == 0 or rng.random() < 0.7,
        })
    day_end = 9 * 60 + rng.randrange(3 * 60, 10 * 60, 15)
    return make_instance(pois, travel, ("09:00", to_hhmm(day_end)))


class SolverTestCase(unittest.TestCase):
    def assert_valid_plan(self, instance: dict, out: dict) -> None:
        self.assertTrue(out["feasible"], out.get("reason"))
        self.assertEqual(ttdp_tool.check(instance, out), [])

    def assert_infeasible(self, out: dict) -> None:
        self.assertFalse(out["feasible"])
        self.assertEqual(out["itinerary"], [])
        self.assertTrue(out["reason"])


class TestInstances(SolverTestCase):
    def test_all_instances_match_ground_truth(self) -> None:
        paths = sorted((ROOT / "testcases").glob("*/*.instance.json"))
        self.assertEqual(len(paths), 10)
        for path in paths:
            with self.subTest(path.name):
                instance = json.loads(path.read_text())
                answer = json.loads(path.with_name(path.name.replace(".instance", ".answer")).read_text())
                out = solve(instance)
                if answer["feasible"]:
                    self.assert_valid_plan(instance, out)
                else:
                    self.assert_infeasible(out)


class TestEdgeCases(SolverTestCase):
    TRAVEL = {"H": {"A": 10, "B": 20}, "A": {"H": 10, "B": 15}, "B": {"H": 20, "A": 15}}

    def one_poi(self, window: tuple[str, str], day_end: str) -> dict:
        return make_instance([{"id": "A", "window": window, "duration": 60}],
                             {"H": {"A": 10}, "A": {"H": 10}}, ("09:00", day_end))

    def test_no_must_visit_is_an_empty_plan(self) -> None:
        instance = make_instance([{"id": "A", "window": ("09:00", "17:00"), "duration": 30, "must": False}],
                                 {"H": {"A": 10}, "A": {"H": 10}}, ("09:00", "17:00"))
        out = solve(instance)
        # Not run through ttdp_tool.check, which crashes on a plan with no stops.
        self.assertTrue(out["feasible"])
        self.assertEqual(out["itinerary"], [])

    def test_exact_fit_at_every_boundary(self) -> None:
        # Arrive 09:10 as A opens, leave 10:10 as it closes, back 10:20 as the day ends.
        instance = self.one_poi(("09:10", "10:10"), "10:20")
        out = solve(instance)
        self.assert_valid_plan(instance, out)
        self.assertEqual(out["itinerary"][0]["start"], "09:10")

    def test_one_minute_short_on_day_end(self) -> None:
        self.assert_infeasible(solve(self.one_poi(("09:10", "10:10"), "10:19")))

    def test_one_minute_short_on_closing_time(self) -> None:
        self.assert_infeasible(solve(self.one_poi(("09:10", "10:09"), "10:20")))

    def test_waits_until_opening(self) -> None:
        instance = self.one_poi(("11:00", "17:00"), "17:00")
        out = solve(instance)
        self.assert_valid_plan(instance, out)
        self.assertEqual(out["itinerary"][0]["start"], "11:00")

    def test_order_forced_by_windows(self) -> None:
        # B closes early, so it must come first even though A is closer.
        instance = make_instance([
            {"id": "A", "window": ("09:00", "17:00"), "duration": 60},
            {"id": "B", "window": ("09:00", "10:30"), "duration": 60},
        ], self.TRAVEL, ("09:00", "17:00"))
        out = solve(instance)
        self.assert_valid_plan(instance, out)
        self.assertEqual([s["poi"] for s in out["itinerary"]], ["B", "A"])

    def test_optional_poi_is_dropped(self) -> None:
        instance = make_instance([
            {"id": "A", "window": ("09:00", "17:00"), "duration": 60},
            {"id": "B", "window": ("09:00", "17:00"), "duration": 60, "must": False},
        ], self.TRAVEL, ("09:00", "17:00"))
        out = solve(instance)
        self.assert_valid_plan(instance, out)
        self.assertEqual([s["poi"] for s in out["itinerary"]], ["A"])


class TestRandomCrossCheck(SolverTestCase):
    """Compare feasibility with the exhaustive search in ttdp_tool on random instances."""

    def test_matches_exhaustive_search(self) -> None:
        rng = random.Random(4263)
        outcomes = {True: 0, False: 0}
        for k in range(300):
            instance = random_instance(rng)
            with self.subTest(k=k):
                expected = bool(ttdp_tool.solve_all(ttdp_tool.Inst(instance)))
                out = solve(instance)
                self.assertEqual(out["feasible"], expected)
                if expected:
                    self.assert_valid_plan(instance, out)
                    optional = {p["id"] for p in instance["pois"] if not p["must_visit"]}
                    self.assertFalse(optional & {s["poi"] for s in out["itinerary"]})
                outcomes[expected] += 1
        # Guard against a generator that only produces one kind of instance.
        self.assertGreaterEqual(min(outcomes.values()), 50, outcomes)


if __name__ == "__main__":
    unittest.main()
