"""Quick script to run a single testcase and see the LLM output.

Usage:
    python run_one.py <testcase_id> [solver]

    testcase_id can be a number (1–5) or a number with variant (1-X, 2-X, …)

Examples:
    python run_one.py 1              # testcase 1, baseline solver
    python run_one.py 1-X            # testcase 1-X variant, baseline solver
    python run_one.py 1 cot          # testcase 1, Chain-of-Thought
    python run_one.py 1-X cot        # testcase 1-X variant, Chain-of-Thought
    python run_one.py 2 self_refine  # testcase 2, Self-Refine
    python run_one.py 3 verifier_loop
    python run_one.py 4 self_consistency

Solvers: baseline (default), cot, self_refine, verifier_loop, self_consistency, combined
"""

import json
import sys
import ttdp_tool as T
from solvers import llm

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    tc = sys.argv[1]  # e.g. "1" or "1-X"
    solver_name = sys.argv[2] if len(sys.argv) > 2 else "baseline"

    solvers = {
        "baseline":         llm.solve,
        "cot":              llm.solve_cot,
        "self_refine":      llm.solve_self_refine,
        "verifier_loop":    llm.solve_verifier_loop,
        "self_consistency": llm.solve_self_consistency,
        "combined":         llm.solve_combined,
    }

    if solver_name not in solvers:
        print(f"Unknown solver '{solver_name}'. Choose from: {', '.join(solvers)}")
        sys.exit(1)

    # folder is always testcase_{base} (e.g. testcase_1), file uses the full id (e.g. testcase_1-X)
    base = tc.split("-")[0]
    path = f"testcases/testcase_{base}/testcase_{tc}.instance.json"
    with open(path) as f:
        instance = json.load(f)

    print(f"Running testcase {tc} with solver '{solver_name}'...\n")
    result = solvers[solver_name](instance)

    print("=== LLM OUTPUT ===")
    print(json.dumps(result, indent=2))

    violations = T.check(instance, result)
    print("\n=== CHECKER RESULT ===")
    if not violations:
        print("VALID")
    else:
        print("VIOLATIONS:")
        for v in violations:
            print(f"  - {v}")

if __name__ == "__main__":
    main()
