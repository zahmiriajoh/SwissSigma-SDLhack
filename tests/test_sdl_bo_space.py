from itertools import combinations
from math import comb

import numpy as np
import pytest

from SDL_BO import space
from production import config


def expected_count(step_ul):
    """Allowed solvent subsets x ways to split TOTAL_UL into that many positive multiples of step_ul."""
    n_steps = space.TOTAL_UL // step_ul
    return sum(comb(n_steps - 1, k - 1) for k in range(1, space.MAX_SOLVENTS_PER_MIXTURE + 1)
               for names in combinations(space.GREEN_SOLVENTS, k) if config.is_allowed(names))


def test_enumerate_mixtures_obeys_robot_constraints():
    mixtures = space.enumerate_mixtures()
    assert mixtures.shape == (expected_count(space.STEP_UL), len(space.GREEN_SOLVENTS))
    assert (mixtures.sum(axis=1) == space.TOTAL_UL).all()
    nonzero = mixtures[mixtures > 0]
    assert (nonzero >= space.MIN_UL).all() and (nonzero % space.STEP_UL == 0).all()
    assert ((mixtures > 0).sum(axis=1) <= space.MAX_SOLVENTS_PER_MIXTURE).all()
    assert len({space.mixture_key(row) for row in mixtures}) == len(mixtures)  # no duplicates


def test_coarse_grid_is_read_at_call_time(coarse_grid):
    assert len(space.enumerate_mixtures()) == expected_count(coarse_grid) < expected_count(5)


def test_ul_fraction_round_trip():
    ul = np.array([[150, 150, 0, 0, 0, 0], [100, 100, 100, 0, 0, 0]])
    fractions = space.to_fractions(ul)
    assert np.allclose(fractions.sum(axis=1), 1)
    assert (space.to_ul(np.round(fractions, 4)) == ul).all()  # survives bo_bridge's 4-decimal CSVs
    assert space.mixture_key(ul[0]) == (150, 150, 0, 0, 0, 0)


def test_solvent_budget_matches_one_trough_per_solvent():
    assert space.solvent_budget_ul() == pytest.approx(0.98 * 24000 / (3 * 4))
    assert space.solvent_budget_ul(n_solutes=2) == pytest.approx(2 * space.solvent_budget_ul())


def test_enumerated_mixtures_avoid_forbidden_pairs(coarse_grid):
    mixtures = space.enumerate_mixtures()
    used = [[s for s, ul in zip(space.GREEN_SOLVENTS, row) if ul > 0] for row in mixtures]
    assert all(config.is_allowed(names) for names in used)
    if config.FORBIDDEN_PAIRS:  # the forbidden binaries themselves are missing, everything else is still there
        a, b = sorted(next(iter(config.FORBIDDEN_PAIRS)))
        assert not any(set(names) == {a, b} for names in used)
        assert any(set(names) == {a, space.GREEN_SOLVENTS[1]} for names in used) or a == space.GREEN_SOLVENTS[1]
