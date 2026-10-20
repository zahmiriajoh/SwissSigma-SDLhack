"""The search space: which solvents exist and which mixtures may be proposed.

Reads `production/config.toml` (via production.config), the same source `OT protocols/bo_bridge.py` reads: the robot
dispenses integer microlitres summing to TOTAL_UL, every used solvent at least MIN_UL. A mixture is stored as
integer uL of each green solvent, which avoids float trouble when comparing mixtures.

    uL  [150, 150, 0, 0, 0, 0]  <->  fractions  [0.5, 0.5, 0, 0, 0, 0]  (50% of the first two green solvents)

Candidates are proposed in STEP_UL steps, so bo_bridge dispenses them exactly as proposed. The reference solvent
(DMF) is the one to replace: bo_bridge adds it as a pure control well, and it is never a model input.
"""
from itertools import combinations

import numpy as np

from production.config import (ALL_SOLVENTS, FIRST_CONDITION, FIRST_ROUND, MAX_SOLVENTS_PER_MIXTURE, MIN_UL,  # noqa: F401
                               N_PLATES, REFERENCE_SOLVENT, SOLUTES, TOTAL_UL, TROUGH_USABLE_UL, is_allowed)

GREEN_SOLVENTS = [s for s in ALL_SOLVENTS if s != REFERENCE_SOLVENT]  # the model's inputs
FRACTION_COLUMNS = [f"frac_{s}" for s in ALL_SOLVENTS]  # bo_bridge column names
GREEN_FRACTION_COLUMNS = [f"frac_{s}" for s in GREEN_SOLVENTS]
N_SOLUTES = len(SOLUTES)

STEP_UL = 5  # resolution of proposed mixtures (>= MIN_UL, divides TOTAL_UL)
assert STEP_UL >= MIN_UL and TOTAL_UL % STEP_UL == 0

# Reservoir limit: one trough per solvent feeds every plate and solute block, so the conditions of a round may together
# use at most TROUGH_USABLE_UL / (N_PLATES * n_solutes) of each solvent. BUDGET_MARGIN leaves room for bo_bridge's
# rounding to whole uL.
BUDGET_MARGIN = 0.98


def solvent_budget_ul(n_solutes=N_SOLUTES) -> float:
    """Largest total single-well volume of one solvent over all conditions of a round that still fits its trough."""
    return BUDGET_MARGIN * TROUGH_USABLE_UL / (N_PLATES * n_solutes)


def _split_into_positive_parts(n_parts: int, total: int):
    """Yield every way to write `total` as an ordered sum of `n_parts` positive integers."""
    if n_parts == 1:
        yield (total,)
        return
    for first in range(1, total - n_parts + 2):  # leave at least 1 for each remaining part
        for rest in _split_into_positive_parts(n_parts - 1, total - first):
            yield (first, *rest)


def enumerate_mixtures(step_ul=None) -> np.ndarray:
    """Every proposable mixture (pure solvents included) as integer uL (n_mixtures, n_green); rows sum to TOTAL_UL.
    Combinations containing a forbidden (immiscible) pair from the config are left out."""
    step_ul = step_ul or STEP_UL  # read at call time so tests can coarsen the grid
    n_solvents, n_steps = len(GREEN_SOLVENTS), TOTAL_UL // step_ul
    mixtures = []
    for n_used in range(1, MAX_SOLVENTS_PER_MIXTURE + 1):
        for indices in combinations(range(n_solvents), n_used):
            if not is_allowed([GREEN_SOLVENTS[i] for i in indices]):
                continue
            for parts in _split_into_positive_parts(n_used, n_steps):
                row = np.zeros(n_solvents, dtype=int)
                row[list(indices)] = np.array(parts) * step_ul
                mixtures.append(row)
    return np.array(mixtures)


def to_ul(fractions) -> np.ndarray:
    """Volume fractions (0-1) -> integer uL, rounding away float noise."""
    return np.rint(np.asarray(fractions, dtype=float) * TOTAL_UL).astype(int)


def to_fractions(ul) -> np.ndarray:
    """Integer uL -> volume fractions (0-1)."""
    return np.asarray(ul, dtype=float) / TOTAL_UL


def mixture_key(ul) -> tuple:
    """Hashable identifier of a mixture (its green-solvent uL), used to find repeats and 'already tested'."""
    return tuple(map(int, ul))
