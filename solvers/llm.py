"""Solution B: LLM planner — baseline and safeguards.

Requires:
    pip install google-genai pydantic
    GEMINI_API_KEY environment variable set.
"""

import json
import os
from typing import List

from pydantic import BaseModel, Field
from google import genai

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

This is a satisfaction problem — any plan that meets all constraints is equally correct.

INSTANCE FIELDS: 
day_window          {start, end} — the day boundaries in HH:MM.
start_location      The label (e.g. "H") where the day starts and ends.
return_to_start     If true, the itinerary must begin and end at start_location.
allow_waiting       Always true — you may wait at a POI until it opens.
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
The whole itinerary must fit within day_window [start, end].
Since return_to_start is true, also account for the travel legs to and from start_location:
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

MODEL = "gemini-3.5-flash"
os.environ["GEMINI_API_KEY"] = "" # INSERT API KEY HERE
client = genai.Client()

# Chain of Thought (CoT) prompting output schema — same as baseline but with a reasoning field prepended

class TTDPOutputCoT(BaseModel):
    reasoning: str = Field(
        description=(
            "Step-by-step constraint analysis before deciding. "
            "For each must-visit POI: confirm its window fits the day. "
            "Then try orderings, compute exact start/end times, and verify "
            "C1–C4 for every stop and the return leg before committing."
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
            "If feasible=false, explain which constraint(s) make every ordering impossible. "
            "Empty string when feasible=true."
        )
    )

# Self-verification schema and system instruction

class VerificationResult(BaseModel):
    valid: bool = Field(
        description="True if the plan satisfies every constraint, False if any constraint is violated."
    )
    violations: List[str] = Field(
        description=(
            "List of constraint violations found. Each entry names the constraint and the POI or leg "
            "where it fails, e.g. 'C1: POI B ends at 10:15 but window closes at 10:00'. "
            "Empty list when valid=true."
        )
    )

VERIFY_SYSTEM_INSTRUCTION = """You are a constraint checker for the Tourist Trip Design Problem (TTDP).

You will be given a TTDP instance and a proposed itinerary. Check every constraint below against
the plan and report any violations. Be precise: compute the exact times.

INSTANCE FIELDS (same as the planner):
day_window          {start, end} — the day boundaries in HH:MM.
start_location      Where the day starts and ends.
return_to_start     Always true — check the return leg too.
opening_windows     [open, close] in HH:MM. The visit [start, end] must fit inside one window.
visit_duration      In whole minutes. end = start + visit_duration.
travel_times        travel_times[from][to] = minutes.

CONSTRAINTS TO CHECK:
C1 Opening hours: each stop's [start, end] must fit entirely within one of its opening_windows.
C2 Travel time: for each consecutive pair i → j, end(i) + travel_times[i][j] ≤ start(j).
   Also check the first leg: day_window.start + travel_times[start_location][first_poi] ≤ start(first_poi).
C3 Day window: end(last_poi) + travel_times[last_poi][start_location] ≤ day_window.end.
C4 Must-visit: every POI with must_visit=true appears exactly once in the itinerary.

Check every constraint. If all pass, set valid=true and violations=[].
If any fail, set valid=false and list each violation clearly.
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
        "Check this proposed TTDP plan against the instance and report any constraint violations.\n\n"
        "INSTANCE:\n" + json.dumps(instance, indent=2)
        + "\n\nPROPOSED PLAN:\n" + json.dumps(plan, indent=2)
    )

def _retry_prompt(instance: dict, violations: List[str]) -> str:
    violations_text = "\n".join(f"  - {v}" for v in violations)
    return (
        "Your previous plan had the following constraint violations:\n"
        + violations_text
        + "\n\nFix all violations and return a corrected plan for this instance:\n\n"
        + json.dumps(instance, indent=2)
    )

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

        # Infeasibility claims need no verification
        if not result.feasible:
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

        if verification.valid:
            return result.model_dump()

        # Step 3: re-prompt with violations for next attempt
        prompt = _retry_prompt(instance, verification.violations)

    # Return the last plan even if verification still failed
    return result.model_dump()
