"""The search space: which solvents exist and which mixtures we are allowed to test.

A mixture is stored as integer "grid units" of each green solvent. With GRID_STEPS = 40, one unit
is 2.5% of the volume, and the units of a mixture add up to 40. Using integers (not fractions)
avoids floating-point trouble when we compare mixtures or look one up in the history.

    grid units  [0, 10, 30, 0, 0, 0]  <->  fractions  [0, 0.25, 0.75, 0, 0, 0]
                                           i.e. 25% acetone + 75% EtOH

DMF is deliberately not part of the search space. It is the solvent we want to replace, so it only
appears as a pure control (see REFERENCE_SOLVENT) and is never mixed with the green solvents.
"""
from itertools import combinations

import numpy as np

# Column order used everywhere (history CSV, candidates CSV, model inputs).
ALL_SOLVENTS = ["DMF", "acetone", "EtOH", "iPrOH", "water", "iPrOAc", "tBuOAc"]
REFERENCE_SOLVENT = "DMF"  # pure control run every round; never mixed, never optimized
GREEN_SOLVENTS = [s for s in ALL_SOLVENTS if s != REFERENCE_SOLVENT]  # the model's 6 inputs

GRID_STEPS = 40  # a mixture's grid units sum to this; 40 steps = 2.5% resolution
MAX_SOLVENTS_PER_MIXTURE = 3


def _split_into_positive_parts(n_parts: int, total: int):
    """Yield every way to write `total` as an ordered sum of `n_parts` positive integers.

    Example: n_parts=2, total=4 yields (1, 3), (2, 2), (3, 1).
    """
    if n_parts == 1:
        yield (total,)
        return
    # The first part leaves at least 1 unit for each of the remaining parts.
    for first_part in range(1, total - n_parts + 2):
        for remaining_parts in _split_into_positive_parts(n_parts - 1, total - first_part):
            yield (first_part, *remaining_parts)


def enumerate_mixtures(grid_steps=None) -> np.ndarray:
    """Every allowed mixture (pure solvents included) as integer grid units (n_mixtures, 6); rows sum to `grid_steps`."""
    grid_steps = grid_steps or GRID_STEPS  # the argument lets tests try other grids
    n_solvents = len(GREEN_SOLVENTS)
    mixtures = []
    for n_used in range(1, MAX_SOLVENTS_PER_MIXTURE + 1):
        for solvent_indices in combinations(range(n_solvents), n_used):  # which solvents take part
            for units_each in _split_into_positive_parts(n_used, grid_steps):  # how the volume is divided
                row = np.zeros(n_solvents, dtype=int)
                row[list(solvent_indices)] = units_each
                mixtures.append(row)
    return np.array(mixtures)


def to_grid_units(fractions) -> np.ndarray:
    """Convert volume fractions (0-1) to integer grid units, rounding away float noise."""
    return np.rint(np.asarray(fractions, dtype=float) * GRID_STEPS).astype(int)


def to_fractions(grid_units) -> np.ndarray:
    """Convert integer grid units to volume fractions (0-1)."""
    return np.asarray(grid_units, dtype=float) / GRID_STEPS


def mixture_key(grid_units) -> tuple:
    """A hashable identifier for a mixture, used to find replicates and detect 'already tested'."""
    return tuple(map(int, grid_units))
