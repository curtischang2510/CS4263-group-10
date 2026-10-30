#!/usr/bin/env python3
"""Run every solver in solvers/ over every test case in testcases/.

  python run_tests.py         # all solvers
  python run_tests.py csp     # one solver, by its name in solvers.SOLVERS

Cases run easy -> medium -> hard. The run stops at the first failure and prints why.
A solver that still raises NotImplementedError is skipped.

Grading follows "Correct output" in the README: on a feasible instance the output must be
an itinerary the checker accepts; on an infeasible instance it must say "feasible": false.
Exit code 0 if nothing failed, 1 otherwise.
"""
import glob, os, sys, time
import ttdp_tool as T
from solvers import SOLVERS

ROOT = os.path.dirname(os.path.abspath(__file__))
LEVELS = {"easy": 0, "medium": 1, "hard": 2}

def discover():
    cases = []
    for ip in glob.glob(os.path.join(ROOT, "testcases", "**", "*.instance.json"), recursive=True):
        cid = os.path.basename(ip)[:-len(".instance.json")]
        cases.append({"id": cid, "inst": T.load(ip), "ans": T.load(ip[:-len(".instance.json")] + ".answer.json")})
    by_id = {c["id"]: c["ans"] for c in cases}
    for c in cases:  # an infeasible twin without a level inherits its partner's
        c["level"] = c["ans"].get("level") or by_id.get(c["ans"].get("twin_of"), {}).get("level", "?")
    return sorted(cases, key=lambda c: (LEVELS.get(c["level"], 9), c["id"]))

def grade(inst, ans, out):
    """Return None if the output is correct, else a short reason."""
    if not isinstance(out, dict) or not isinstance(out.get("feasible"), bool):
        return "output is not a dict with a boolean 'feasible'"
    if not ans["feasible"]:
        return None if not out["feasible"] else "gave an itinerary for an infeasible instance"
    if not out["feasible"]:
        return "claimed infeasible, but the instance is feasible"
    v = T.check(inst, out)
    return None if not v else "violations: " + ", ".join(v)

def run(name, solve, cases):
    """Return 'pass', 'fail' or 'skip' for one solver."""
    print(f"\n== {name}")
    failed = False
    for c in cases:
        t0 = time.time()
        try:
            out = solve(c["inst"]); reason = grade(c["inst"], c["ans"], out)
        except NotImplementedError:
            print("   skipped: not implemented yet"); return "skip"
        except Exception as e:
            reason = f"solver raised {type(e).__name__}: {e}"
        kind = "feasible" if c["ans"]["feasible"] else "infeasible"
        print(f"{'PASS' if reason is None else 'FAIL'}  {c['id']:18s} {c['level']:6s} {kind:10s} {time.time() - t0:6.2f}s")
        if reason:
            print(f"      {reason}"); failed = True
    if failed:
        return "fail"
    print(f"   all {len(cases)} cases passed"); return "pass"

def main():
    names = sys.argv[1:] or list(SOLVERS)
    unknown = [n for n in names if n not in SOLVERS]
    if unknown: sys.exit(f"unknown solver {', '.join(unknown)}; choose from: {', '.join(SOLVERS)}")
    cases = discover()
    results = {}
    for n in names:
        results[n] = run(n, SOLVERS[n], cases)
    print("\n" + ", ".join(f"{n}: {r}" for n, r in results.items()))
    if any(r == "fail" for r in results.values()):
        sys.exit(1)

if __name__ == "__main__":
    main()
