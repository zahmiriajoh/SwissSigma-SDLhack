import numpy as np
import pytest

from SDL_BO import space


def test_enumerate_mixtures_obeys_robot_constraints():
    mixtures = space.enumerate_mixtures()
    assert mixtures.shape == (35_111, 6)
    assert (mixtures.sum(axis=1) == space.TOTAL_UL).all()
    nonzero = mixtures[mixtures > 0]
    assert (nonzero >= space.MIN_UL).all() and (nonzero % space.STEP_UL == 0).all()
    assert ((mixtures > 0).sum(axis=1) <= space.MAX_SOLVENTS_PER_MIXTURE).all()
    assert len({space.mixture_key(row) for row in mixtures}) == len(mixtures)  # no duplicates


def test_coarse_grid_is_read_at_call_time(coarse_grid):
    assert len(space.enumerate_mixtures()) == 6 + 15 * 5 + 20 * 10


def test_ul_fraction_round_trip():
    ul = np.array([[150, 150, 0, 0, 0, 0], [100, 100, 100, 0, 0, 0]])
    fractions = space.to_fractions(ul)
    assert np.allclose(fractions.sum(axis=1), 1)
    assert (space.to_ul(np.round(fractions, 4)) == ul).all()  # survives bo_bridge's 4-decimal CSVs
    assert space.mixture_key(ul[0]) == (150, 150, 0, 0, 0, 0)


def test_solvent_budget_matches_one_trough_per_solvent():
    assert space.solvent_budget_ul() == pytest.approx(0.98 * 24000 / (3 * 4))
    assert space.solvent_budget_ul(n_solutes=2) == pytest.approx(2 * space.solvent_budget_ul())
