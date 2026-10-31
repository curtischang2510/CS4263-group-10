"""Solvers run by `python run_tests.py`. Each takes one parsed instance and returns one
output dict; one that still raises NotImplementedError is skipped. To test another
solver, add it to SOLVERS."""
from . import csp, llm

SOLVERS = {
    "csp":                      csp.solve,                     # Solution A
    "llm":                      llm.solve,                     # Solution B — baseline
    "llm_cot":                  llm.solve_cot,                 # Solution B — safeguard 1: Chain-of-Thought
    "llm_self_refine":          llm.solve_self_refine,         # Solution B — safeguard 2: Self-Refine
    "llm_verifier_loop":        llm.solve_verifier_loop,       # Solution B — safeguard 3: Verifier-in-the-loop
    "llm_self_consistency":     llm.solve_self_consistency,    # Solution B — safeguard 4: Self-consistency
    "llm_combined":             llm.solve_combined,            # Solution B — all safeguards: CoT + Verifier-in-the-loop + Self-consistency
}
