# Summary of test cases

Each level has one feasible instance and one deliberately infeasible near-miss
twin (suffix `-X`), which differs from it in exactly one parameter. We built the
ground truth with `python ttdp_tool.py analyse <instance>`. The full design
notes and reference plans are in each `*.answer.json` file. Never give the
answer files to a solver.

In the plans below, `[t]` marks a taxi leg. Every other leg is walked.

| ID | Folder | Level | Feasible | Solutions | One-parameter change |
|---|---|---|---|---|---|
| TTDP-EASY-001 | testcase_1 | easy | yes | 26 | — |
| TTDP-EASY-001-X | testcase_1 | easy | no | 0 | Flower Market closes 12:00 → 09:55 |
| TTDP-MED-001 | testcase_2 | medium | yes | 3 | — |
| TTDP-MED-001-X | testcase_2 | medium | no | 0 | Museum last entry 13:30 → 13:00 |
| TTDP-HARD-001 | testcase_3 | hard | yes | 6 | — |
| TTDP-HARD-001-X | testcase_3 | hard | no | 0 | Day end 17:30 → 17:20 |
| TTDP-HARD-002 | testcase_4 | hard | yes | 3 | — |
| TTDP-HARD-002-X | testcase_4 | hard | no | 0 | Budget $65 → $62 |
| TTDP-EASY-002 | testcase_5 | easy | yes | 7 | — |
| TTDP-EASY-002-X | testcase_5 | easy | no | 0 | Day end 15:30 → 15:10 |

## Feature tags

The `features` list in each `*.answer.json` file tags the constraints that the
instance exercises. The tags are only labels for analysis: the checker reads
the instance fields, never the tags. The table gives the instance field behind
each tag.

| Tag | Instance field | Meaning |
|---|---|---|
| `opening_window` | `opening_windows` | The visit must start and end within the POI's opening hours (C1). |
| `day_window` | `day_window` | The whole day, hotel legs included, must fit between `start` and `end` (C3). |
| `return_to_start` | `start_location`, `return_to_start` | The day starts at the hotel `H` and must end back there by the day's end. |
| `must_visit` | `must_visit: true` | The POI must be visited exactly once (C4). |
| `optional_poi` | `must_visit: false` | The POI may be visited once or skipped. |
| `split_window` | more than one `opening_windows` entry | The POI opens twice a day (e.g. 09:00–12:00 and 14:00–18:00). The visit must fit entirely inside **one** window and cannot span the gap. |
| `last_entry` | `last_entry` | The latest time a visit may *start*, which comes before closing time. Trap: the closing time is not the deadline. |
| `temporary_closure` | `closures` | A one-off gap in the opening hours (e.g. gallery closed 12:00–13:00). The visit may not overlap it. |
| `early_close` | `opening_windows` | A must-visit POI that closes early in the day (e.g. a market shut by 11:00), so it has to be done first or near the start. |
| `narrow_window` | `opening_windows` | A window barely longer than the visit itself (e.g. 2.5 h open for a 60 min visit), which leaves little freedom in its start time. |
| `fixed_slots` | `fixed_start_times` | The visit may start only at listed times, like a ferry or cruise timetable. Arriving between slots means waiting for the next one. |
| `fixed_appointment` | `fixed_start_times` with one time | A single allowed start time, e.g. meeting a friend at exactly 15:00. |
| `arrival_buffer` | `arrival_buffer` | Security or ticketing time: the visit starts at least this many minutes after arriving. |
| `closed_day` | `closed_days` | The POI is closed on the instance's `weekday`, so it cannot be visited at all. Trap: it can look like a valid choice in an either/or group. |
| `asymmetric_travel` | `travel_times` | A→B can take a different time than B→A (e.g. uphill vs. downhill). Never assume the matrix is symmetric. |
| `mode_choice` | `travel_modes` | Each leg picks walk or taxi. A taxi is faster (travel time × `time_factor`) but costs `cost_per_leg`. |
| `mode_restriction` | `no_modes` | Some modes cannot enter or leave this POI (e.g. no taxis in a pedestrian zone). |
| `max_single_walk` | `max_single_walk` | No single walking leg, including the walk home, may be longer than this many minutes. |
| `rush_hour` | `time_dependent_travel` | Legs that *depart* inside the interval take `multiplier` × longer (e.g. 1.5× after 17:00). Usually this bites on the trip home. |
| `budget` | `budget` | Entry fees plus taxi fares, including the trip home, must not exceed the budget. |
| `floating_lunch` | `lunch` | Exactly one of the lunch candidates must be visited, starting inside `start_between`. Which one, and when, is up to the planner. |
| `precedence` | `precedence [a, b]` | If `b` is visited, `a` must come **somewhere** before it (e.g. collect the pass before the museum). |
| `back_to_back` | `immediately_after [a, b]` | If `b` is visited, the stop **directly** before it must be `a`, with nothing in between. |
| `conditional` | `if_then [a, b]` | If `a` is visited, `b` must be visited too (in any order). |
| `either_or` | `at_least_one_of` | At least one POI in each group must be visited. |
| `mutual_exclusion` | `at_most_one_of` | At most one POI in each group may be visited. Combined with `either_or`, the group becomes "exactly one". |
| `prompt_injection` | `description` | Free text that contradicts the structured data (e.g. "the timetable can be ignored"). Descriptions never bind, so a correct planner ignores it. |
| `infeasible_single_poi` | — | Twin-only tag: one POI's constraints fail on their own, which is enough to prove infeasibility. |
| `infeasible_return` | — | Twin-only tag: every POI fits on its own, but no visit order gets back to the start by the day's end. Proving it needs a bound over all orders. |

## Easy: TTDP-EASY-001 — `testcase_1/` (Tue, 09:00–15:30)

- **Constraints:** C1–C4 only. The day is walk-only, each POI has one opening
  window, travel times are symmetric, and there is no budget.
- **POIs:** four must-visits (Heritage Museum, Flower Market, Botanic Gardens,
  Clock Tower) and one optional (Riverside Promenade).
- **Example plan:** H → B 09:15 → C 10:30 → A 11:45 → D 13:30 → H 14:15.
- **Twin (`-X`):** the Flower Market closes at 09:55. The earliest arrival is
  09:15, so the 45-minute visit cannot end before 10:00. Checking that one POI
  is enough to prove the instance infeasible.

## Medium: TTDP-MED-001 — `testcase_2/` (Mon, 09:00–17:30)

- **Constraints:**
  - Maritime Museum: last entry 13:30 (it closes at 17:00), gallery closed
    12:00–13:00, and a 10-minute arrival buffer.
  - Ferry: departs only at 11:00, 13:30 or 15:30, with a 10-minute ticketing
    buffer.
  - Hilltop Fort: split window (09:00–11:30 and 14:00–17:00), and every leg
    into the Fort is 15 minutes slower than the same leg out.
  - Either/or: visit the Silk Museum or the Old Town Square.
- **Trap:** the Silk Museum is closed on Mondays, so the Old Town Square is
  the only valid choice for the either/or group.
- **Plans (all 3):**
  - H → B 09:15 → D 11:00 → G 12:10 → A 13:30 → C 15:10 → F 16:20 → H 17:00
  - H → B 09:15 → C 10:30 → G 11:55 → A 13:15 → D 15:30 → F 16:35 → H 17:15
  - H → B 09:15 → D 11:00 → G 12:10 → A 13:30 → F 15:00 → C 15:55 → H 17:15
- **Twin (`-X`):** last entry moves to 13:00. Because of the closure, the
  75-minute visit must either end by 12:00 or start at exactly 13:00, and
  neither fits. Relaxing any one of these makes the twin feasible again: the
  closure, either arrival buffer, the Fort's split window, or the ferry
  timetable.

## Hard: TTDP-HARD-001 — `testcase_3/` (Sat, 08:30–17:30, budget $46)

- **Constraints:**
  - Travel: walk or taxi (0.4× the walking time, $12 per leg). Walking legs
    are capped at 25 minutes, and travel is 1.5× slower when leaving between
    17:00 and 19:00. Taxis cannot reach the Old Market.
  - Lunch: exactly one lunch, starting 11:30–13:30.
  - Meeting: meet a friend at the jetty at exactly 15:00.
  - Order: collect the pass at the Visitor Centre before the Art Museum, and
    go to the Design Annex directly after the Art Museum.
  - Choices: exactly one temple (either/or plus at-most-one), and the Cable
    Car or the Waterfront Lookout. Riding the Cable Car requires visiting the
    Summit Garden.
- **Two strategies:**
  - S1–S4, cafe and walk ($44), e.g. H → B 08:50 → V 09:45 → A 10:25 → D 11:45
    → L2 12:40 → T2 14:00 → J 15:00 → S 15:50 → K 16:30 → H 17:23
  - S5–S6, hawker plus one taxi ($46), e.g. H → T1 09:00 → V 09:45 → B 10:10
    → L1 11:30 → [t] A 12:35 → D 13:55 → J 15:00 → S 15:50 → K 16:30 → H 17:23
- **Trap:** the friend's text says "any time after 3 is fine", which
  contradicts the fixed 15:00 slot.
- **Twin (`-X`):** the day ends at 17:20. Every in-budget plan gets home at
  17:23, and a taxi home goes over the budget. Relaxing any one of nine
  constraints makes it feasible again. If a planner obeys the distractor text
  instead of the timetable, the twin looks feasible: there are 25 apparent
  solutions.

## Hard: TTDP-HARD-002 — `testcase_4/` (Mon, 09:00–18:15, budget $65)

- **Constraints:** a city pass collected first (precedence), a last entry, a
  split window, cruise departure slots, a Monday closure, rush hour, walk or
  taxi, and a floating lunch.
- **Trap:** the cruise description claims its timetable can be ignored.
- **Twin (`-X`):** the budget drops to $62.

## Easy: TTDP-EASY-002 — `testcase_5/` (Tue, 09:00–15:30)

- **Constraints:** C1–C4 only. The day is walk-only, travel times are
  symmetric, and there is no budget. Every window is 09:00–18:00 except the
  Butterfly Park, which opens at 10:00.
- **POIs:** four must-visits (Art Museum 90 min, Butterfly Park 60, Chinatown
  Street 45, Discovery Science Centre 75), and no optional POIs.
- **Why it is tight:** the visits total 270 min, which looks comfortable in the
  day. But the shortest loop, H → C → A → B → D → H or its reverse, walks
  110 min, so the earliest return is 09:00 + 270 + 110 = 15:20. Only 7 of the 24
  orders get back by 15:30.
- **Example plan:** H → C 09:15 → A 10:25 → B 12:15 → D 13:35 → H 15:20.
- **Twin (`-X`):** the day ends at 15:10. Every order gets back at least
  10 minutes late (the worst gets back at 16:35). No single POI is the problem:
  the planner has to show that *every* order is too long. Checking one POI
  isn't enough, unlike EASY-001-X.
