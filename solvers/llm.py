"""Solution B: LLM planner — baseline and safeguards.

Requires:
    pip install google-genai pydantic
    GEMINI_API_KEY environment variable set.

Usage (run all tests via the test runner):
    python run_tests.py llm                   # baseline
    python run_tests.py llm_cot               # safeguard 1: Chain-of-Thought
    python run_tests.py llm_self_verify       # safeguard 2: Self-verification
    python run_tests.py llm_verifier_loop     # safeguard 3: Verifier-in-the-loop
    python run_tests.py llm_self_consistency  # safeguard 4: Self-consistency (5x API calls)
    python run_tests.py llm llm_cot llm_self_verify llm_verifier_loop llm_self_consistency  # all

"""

import json
import os
import sys
from collections import Counter
from typing import List

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import ttdp_tool as T

from pydantic import BaseModel, Field
from google import genai
from google.genai import types

# Output schema

class ItineraryStop(BaseModel):
    poi: str = Field(description="POI id exactly as it appears in the instance")
    mode: str = Field(description="Travel mode for the leg arriving at this POI (e.g. walk, taxi)")
    start: str = Field(description="Visit start time in HH:MM")
    end: str = Field(description="Visit end time in HH:MM (= start + visit_duration)")

class TTDPOutput(BaseModel):
    feasible: bool = Field(
        description="True if a valid itinerary was found, False if no feasible plan exists"
    )
    itinerary: List[ItineraryStop] = Field(
        description="Ordered list of POI visits. Must be empty when feasible=false."
    )
    return_mode: str = Field(
        description=(
            "Travel mode for the return leg back to start_location. "
            "Use 'walk' when no travel_modes are defined in the instance."
        )
    )
    reason: str = Field(
        description=(
            "If feasible=false, explain which constraint(s) make every ordering impossible. "
            "Empty string when feasible=true."
        )
    )

# System instruction

SYSTEM_INSTRUCTION = """You are a constraint-satisfaction planner solving the Tourist Trip Design Problem (TTDP).

Given a TTDP instance in JSON, either:
  (a) Produce a feasible one-day itinerary satisfying every constraint below, or
  (b) Set feasible=false if no valid itinerary exists and explain why in reason.

This is a satisfaction problem — any plan that meet,s all constraints is equally correct.

INSTANCE FIELDS:
day_window          {start, end} — the day boundaries in HH:MM.
start_location      The label (e.g. "H") where the day begins.
return_to_start     The itinerary must return to start_location by day_window.end.
                    The output field return_mode specifies the travel mode for that final leg.
allow_waiting       You may arrive at a POI before it opens and wait.
pois                List of points of interest. Each POI has:
  id                  Short label used in travel_times and the output.
  opening_windows     List of [open, close] pairs in HH:MM. The visit must fit entirely inside one window.
  visit_duration      How long the visit takes, in whole minutes.
  must_visit          If true, this POI must appear in the itinerary exactly once.
travel_times        Nested object: travel_times[from][to] = travel time in whole minutes.

CONSTRAINTS:
C1 Opening hours
Every visit must start AND end within one of the POI's opening_windows.
If there are multiple windows, the entire visit [start, end] must fit inside ONE window.

C2 Travel time
For consecutive stops i → j: end_time(i) + travel_times[i][j] ≤ start_time(j).
All travel is on foot; use mode="walk" for every stop and for the return leg.
Waiting is allowed — if you arrive before a POI opens, you wait.

C3 Day window
The itinerary must fit within day_window [start, end], including the legs to and from start_location:
  day_window.start + travel_times[start_location][first_poi] ≤ start_time(first_poi)
  end_time(last_poi) + travel_times[last_poi][start_location] ≤ day_window.end

C4 Must-visit
Every POI with must_visit=true must appear in the itinerary exactly once.
Optional POIs (must_visit=false) may be included at most once, or skipped.

ARITHMETIC RULES: 
• All times are whole minutes internally; display as HH:MM in the output.
• end_time for a stop = start_time + visit_duration.
• The itinerary list must be in the order the POIs are visited.
"""

MODEL = "gemini-3.5-flash-lite"
os.environ["GEMINI_API_KEY"] = "AQ.Ab8RN6KwZ2vkhEAU2cvTXrgp0lO3NHHUyEI71AsbMuTGba2fbg" # INSERT API KEY HERE
client = genai.Client()

DEBUG = True  # Set to True to print LLM reasoning and intermediate steps

def _debug(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)

# Safeguard #1: 
# Chain of Thought (CoT) prompting output schema — same as baseline but with a reasoning field prepended

class TTDPOutputCoT(BaseModel):
    reasoning: str = Field(
        description=(
            "A chain of intermediate reasoning steps that lead to the final answer. "
            "Note which POIs are most time-constrained, derive a candidate ordering, then compute "
            "exact arrival and start times at each stop showing the arithmetic explicitly "
            "(e.g. 'B ends 09:45, travel 20 min → arrive A at 10:05, open at 10:00, start 10:05, end 11:35'). "
            "For each stop verify C1 explicitly: start >= open AND end <= close — "
            "both bounds must hold, not just that the POI is open at arrival. "
            "Also verify travel times, the day window return leg, and all must-visits "
            "before committing to the final answer. "
            "If any constraint fails, declare feasible=false."
        )
    )
    feasible: bool = Field(
        description="True if a valid itinerary was found, False if no feasible plan exists"
    )
    itinerary: List[ItineraryStop] = Field(
        description="Ordered list of POI visits. Must be empty when feasible=false."
    )
    return_mode: str = Field(
        description="Travel mode for the return leg. Always 'walk'."
    )
    reason: str = Field(
        description=(
            "If feasible=false, explain which constraint(s) make every ordering impossible. Justify the constraints."
            "Empty string when feasible=true."
        )
    )

# Safeguard 2: Self-verification
# Self-verification schema and system instruction

class VerificationResult(BaseModel):
    valid: bool = Field(
        description="True if the plan satisfies every constraint, False if any constraint is violated."
    )
    violations: List[str] = Field(
        description=(
            "List of specific, actionable feedback items for each constraint violation found. "
            "Each entry must state: which constraint is violated, the exact values that cause the failure, "
            "and what needs to change to fix it. "
            "Example: 'C2: POI B ends at 09:45, travel to A is 25 min → earliest start for A is 10:10, "
            "but plan has A starting at 10:05. Delay A to 10:10 or reorder B after A.' "
            "Empty list when valid=true."
        )
    )

VERIFY_SYSTEM_INSTRUCTION = """You are a constraint checker for the Tourist Trip Design Problem (TTDP).

You will be given a TTDP instance and a proposed itinerary. Check every constraint below
against the plan by computing exact values, and report any violations.

INSTANCE FIELDS:
day_window          {start, end} — the day boundaries in HH:MM.
start_location      Where the day begins and must return to by day_window.end.
return_to_start     The itinerary must return to start_location by day_window.end —
                    check the final return leg (last POI → start_location).
allow_waiting       Waiting is allowed — arriving before a POI opens is not a violation
                    as long as the visit starts within the opening_window.
pois                List of points of interest. Each POI has:
  id                  Short label used in travel_times and the itinerary.
  opening_windows     List of [open, close] pairs in HH:MM. The visit must fit inside one window.
  visit_duration      In whole minutes. end = start + visit_duration.
  must_visit          If true, this POI must appear in the itinerary exactly once.
travel_times        travel_times[from][to] = travel time in whole minutes.

CONSTRAINTS TO CHECK:

C1 Opening hours. For each stop, verify open <= start AND end <= close for at least one
   of the POI's opening_windows. Also verify end - start = visit_duration exactly.

C2 Travel time. Check the first leg:
   earliest_start(first_poi) = day_window.start + travel_times[start_location][first_poi]
   Verify: start(first_poi) >= earliest_start.
   For each consecutive pair i → j:
   earliest_start(j) = end(i) + travel_times[i][j]
   Verify: start(j) >= earliest_start(j).

C3 Day window. Check the return leg:
   return_arrival = end(last_poi) + travel_times[last_poi][start_location]
   Verify: return_arrival <= day_window.end.

C4 Must-visit. For each POI with must_visit=true, verify it appears exactly once
   in the itinerary.

If all constraints pass, set valid=true and violations=[].
If any fail, set valid=false. For each violation, show the exact values that reveal
the failure and state what needs to change to fix it.
"""

# Shared helpers

def _prompt(instance: dict) -> str:
    return (
        "Solve this TTDP instance. "
        "Return a feasible itinerary or set feasible=false with a reason.\n\n"
        + json.dumps(instance, indent=2)
    )

def _verify_prompt(instance: dict, plan: dict) -> str:
    return (
        "Check every constraint in the proposed TTDP plan. "
        "For each violation, compute the exact values, explain why it fails, and state what needs to change.\n\n"
        "INSTANCE:\n" + json.dumps(instance, indent=2)
        + "\n\nPROPOSED PLAN:\n" + json.dumps(plan, indent=2)
    )

def _retry_prompt(instance: dict, history: List[dict]) -> str:
    """history is a list of {"plan": ..., "violations": [...]} dicts, one per failed attempt."""
    parts = []
    for i, entry in enumerate(history):
        violations_text = "\n".join(f"  - {v}" for v in entry["violations"])
        parts.append(
            f"Attempt {i + 1} plan:\n" + json.dumps(entry["plan"], indent=2)
            + f"\nViolations:\n{violations_text}"
        )
    parts.append(
        "All attempts above failed. "
        "Fix all violations and return a corrected plan — "
        "or if the violations cannot be resolved (e.g. the same POI keeps failing regardless of ordering), "
        "set feasible=false and explain why.\n\n"
        "Instance:\n" + json.dumps(instance, indent=2)
    )
    return "\n\n".join(parts)

# Baseline solver

def solve(instance: dict) -> dict:
    """Input: one parsed *.instance.json file.
    Output: a dict in the format of testcases/example_output.json, i.e. a feasible
    itinerary, or {"feasible": False, "itinerary": [], "reason": "..."} if none exists.
    """
    interaction = client.interactions.create(
        model=MODEL,
        system_instruction=SYSTEM_INSTRUCTION,
        input=_prompt(instance),
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": TTDPOutput.model_json_schema(),
        },
    )
    result = TTDPOutput.model_validate_json(interaction.output_text)
    _debug("\n[baseline] feasible:", result.feasible)
    _debug("[baseline] itinerary:", [s.poi for s in result.itinerary])
    if not result.feasible:
        _debug("[baseline] reason:", result.reason)
    return result.model_dump()

# Safeguard 1: Chain-of-Thought

def solve_cot(instance: dict) -> dict:
    """Safeguard 1 — Chain-of-Thought prompting.
    The model writes step-by-step reasoning into the 'reasoning' field before
    committing to an itinerary. The checker ignores that field.
    """
    interaction = client.interactions.create(
        model=MODEL,
        system_instruction=SYSTEM_INSTRUCTION,
        input=_prompt(instance),
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": TTDPOutputCoT.model_json_schema(),
        },
    )
    result = TTDPOutputCoT.model_validate_json(interaction.output_text)
    _debug("\n[cot] reasoning:\n", result.reasoning)
    _debug("[cot] feasible:", result.feasible)
    _debug("[cot] itinerary:", [s.poi for s in result.itinerary])
    if not result.feasible:
        _debug("[cot] reason:", result.reason)
    # Strip the reasoning field before returning so the checker sees the same shape
    return TTDPOutput(
        feasible=result.feasible,
        itinerary=result.itinerary,
        return_mode=result.return_mode,
        reason=result.reason,
    ).model_dump()

# Safeguard 2: Self-verification

MAX_ATTEMPTS = 3

def solve_self_verify(instance: dict) -> dict:
    """Safeguard 2 — Self-verification.
    After each plan, a second LLM call checks every constraint. If violations
    are found, the plan and violation list are sent back to the planner for
    correction. Retries up to MAX_ATTEMPTS times.
    """
    prompt = _prompt(instance)
    history = []

    for attempt in range(MAX_ATTEMPTS):
        # Step 1: generate a plan
        plan_interaction = client.interactions.create(
            model=MODEL,
            system_instruction=SYSTEM_INSTRUCTION,
            input=prompt,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": TTDPOutput.model_json_schema(),
            },
        )
        result = TTDPOutput.model_validate_json(plan_interaction.output_text)
        _debug(f"\n[self_verify] attempt {attempt + 1} — feasible: {result.feasible}")
        _debug(f"[self_verify] itinerary: {[s.poi for s in result.itinerary]}")

        # Infeasibility claims need no verification
        if not result.feasible:
            _debug("[self_verify] infeasible claim, skipping verification")
            return result.model_dump()

        # Step 2: verify the plan
        verify_interaction = client.interactions.create(
            model=MODEL,
            system_instruction=VERIFY_SYSTEM_INSTRUCTION,
            input=_verify_prompt(instance, result.model_dump()),
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": VerificationResult.model_json_schema(),
            },
        )
        verification = VerificationResult.model_validate_json(verify_interaction.output_text)
        _debug(f"[self_verify] verification valid: {verification.valid}")
        if not verification.valid:
            for v in verification.violations:
                _debug(f"  violation: {v}")

        if verification.valid:
            return result.model_dump()

        # Step 3: accumulate history and re-prompt
        history.append({"plan": result.model_dump(), "violations": verification.violations})
        prompt = _retry_prompt(instance, history)

    _debug("[self_verify] max attempts reached, returning last plan")
    # Return the last plan even if verification still failed
    return result.model_dump()

# Safeguard 3: Verifier-in-the-loop

def solve_verifier_loop(instance: dict) -> dict:
    """Safeguard 3 — Verifier-in-the-loop.
    Uses the deterministic ttdp_tool.check() instead of a second LLM call to
    verify each plan. Violations are fed back to the LLM for correction.
    Retries up to MAX_ATTEMPTS times.
    """
    prompt = _prompt(instance)
    history = []  # list of {"plan": ..., "violations": [...]} for each failed attempt

    for attempt in range(MAX_ATTEMPTS):
        # Step 1: generate a plan
        interaction = client.interactions.create(
            model=MODEL,
            system_instruction=SYSTEM_INSTRUCTION,
            input=prompt,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": TTDPOutput.model_json_schema(),
            },
        )
        result = TTDPOutput.model_validate_json(interaction.output_text)
        _debug(f"\n[verifier_loop] attempt {attempt + 1} — feasible: {result.feasible}")
        _debug(f"[verifier_loop] itinerary: {[s.poi for s in result.itinerary]}")

        # Infeasibility claims cannot be verified further — accept and return
        if not result.feasible:
            _debug("[verifier_loop] infeasible claim, returning")
            return result.model_dump()

        # Step 2: run the deterministic checker
        violations = T.check(instance, result.model_dump())
        _debug(f"[verifier_loop] T.check violations: {violations}")

        if not violations:
            return result.model_dump()

        # Step 3: accumulate history and re-prompt with full violation history
        history.append({"plan": result.model_dump(), "violations": violations})
        prompt = _retry_prompt(instance, history)

    _debug("[verifier_loop] max attempts reached, returning last plan")
    return result.model_dump()

# Safeguard 4: Self-consistency

K_SAMPLES = 5
SC_TEMPERATURE = 0.7  # > 0 to produce diverse reasoning paths across samples

def _poi_sequence(plan: dict) -> tuple:
    return tuple(s["poi"] for s in plan.get("itinerary", []))

def _majority_plan(plans: List[dict], instance: dict) -> dict:
    """Aggregate K plans by majority vote on POI sequence, preferring valid plans.

    Self-consistency marginalises over reasoning paths and
    picks the most consistent final answer. Here the 'answer' is the ordered POI
    sequence. Valid plans (those that pass the deterministic checker) are preferred;
    we fall back to raw majority only when none are valid.
    """
    valid, infeasible_claims, invalid = [], [], []
    for p in plans:
        if not p["feasible"]:
            infeasible_claims.append(p)
        elif not T.check(instance, p):
            valid.append(p)
        else:
            invalid.append(p)

    # Majority of samples say infeasible → return an infeasible claim
    if len(infeasible_claims) > len(plans) / 2:
        return infeasible_claims[0]

    # Pick most common sequence among valid plans
    if valid:
        best_seq = Counter(_poi_sequence(p) for p in valid).most_common(1)[0][0]
        return next(p for p in valid if _poi_sequence(p) == best_seq)

    # No valid plans — pick most common sequence among all feasible claims
    feasible = [p for p in plans if p["feasible"]]
    if feasible:
        best_seq = Counter(_poi_sequence(p) for p in feasible).most_common(1)[0][0]
        return next(p for p in feasible if _poi_sequence(p) == best_seq)

    return plans[0]

def solve_self_consistency(instance: dict) -> dict:
    """Safeguard 4 — Self-consistency.
    Samples K independent CoT plans at temperature > 0, then selects the answer
    with the most consistent POI sequence, preferring plans that pass the checker.
    Self-consistency is always combined with CoT per the original paper.
    """
    sc_config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        temperature=SC_TEMPERATURE,
        response_mime_type="application/json",
        response_schema=TTDPOutputCoT,
    )

    plans = []
    for i in range(K_SAMPLES):
        response = client.models.generate_content(
            model=MODEL,
            contents=_prompt(instance),
            config=sc_config,
        )
        raw = TTDPOutputCoT.model_validate_json(response.text)
        _debug(f"\n[self_consistency] sample {i + 1}/{K_SAMPLES}")
        _debug(f"[self_consistency] reasoning:\n{raw.reasoning}")
        _debug(f"[self_consistency] feasible: {raw.feasible}, itinerary: {[s.poi for s in raw.itinerary]}")
        # Strip reasoning field so downstream handling matches other solvers
        plans.append(TTDPOutput(
            feasible=raw.feasible,
            itinerary=raw.itinerary,
            return_mode=raw.return_mode,
            reason=raw.reason,
        ).model_dump())

    selected = _majority_plan(plans, instance)
    _debug(f"\n[self_consistency] selected — feasible: {selected['feasible']}, itinerary: {[s['poi'] for s in selected['itinerary']]}")
    return selected

# Combined: CoT + Verifier-in-the-loop + Self-consistency

def _verifier_loop_one_sample(instance: dict, raw: TTDPOutputCoT) -> dict:
    """Run verifier-in-the-loop correction on one CoT sample.
    Returns the corrected plan as a TTDPOutput dict.
    """
    result = TTDPOutput(
        feasible=raw.feasible,
        itinerary=raw.itinerary,
        return_mode=raw.return_mode,
        reason=raw.reason,
    )
    if not result.feasible:
        return result.model_dump()

    history = []
    for attempt in range(MAX_ATTEMPTS):
        violations = T.check(instance, result.model_dump())
        if not violations:
            return result.model_dump()

        history.append({"plan": result.model_dump(), "violations": violations})
        interaction = client.interactions.create(
            model=MODEL,
            system_instruction=SYSTEM_INSTRUCTION,
            input=_retry_prompt(instance, history),
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": TTDPOutput.model_json_schema(),
            },
        )
        result = TTDPOutput.model_validate_json(interaction.output_text)
        if not result.feasible:
            return result.model_dump()

    return result.model_dump()

def solve_combined(instance: dict) -> dict:
    """Combined safeguards: CoT + Verifier-in-the-loop + Self-consistency.
    Samples K CoT plans, runs verifier-in-the-loop correction on each,
    then aggregates via majority vote over POI sequences.
    """
    sc_config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        temperature=SC_TEMPERATURE,
        response_mime_type="application/json",
        response_schema=TTDPOutputCoT,
    )

    plans = []
    for i in range(K_SAMPLES):
        response = client.models.generate_content(
            model=MODEL,
            contents=_prompt(instance),
            config=sc_config,
        )
        raw = TTDPOutputCoT.model_validate_json(response.text)
        _debug(f"\n[combined] sample {i + 1}/{K_SAMPLES} — feasible: {raw.feasible}, itinerary: {[s.poi for s in raw.itinerary]}")
        corrected = _verifier_loop_one_sample(instance, raw)
        _debug(f"[combined] after correction — feasible: {corrected['feasible']}, itinerary: {[s['poi'] for s in corrected['itinerary']]}")
        plans.append(corrected)

    selected = _majority_plan(plans, instance)
    _debug(f"\n[combined] selected — feasible: {selected['feasible']}, itinerary: {[s['poi'] for s in selected['itinerary']]}")
    return selected
