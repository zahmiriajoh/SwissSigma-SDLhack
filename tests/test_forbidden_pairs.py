"""A mixture containing a forbidden pair is rejected everywhere, whatever the other solvents in it are."""
from itertools import combinations

import numpy as np
import pandas as pd
import pytest

from conftest import DEBUG_DIR, OT_EXAMPLES, run_bridge
from production.config import FIRST_ROUND, FORBIDDEN_PAIRS, GREEN_SOLVENTS, MAX_SOLVENTS_PER_MIX, is_allowed

SUBSETS = [c for n in range(1, MAX_SOLVENTS_PER_MIX + 1) for c in combinations(GREEN_SOLVENTS, n)]


def has_pair(names):
    return any(pair <= set(names) for pair in FORBIDDEN_PAIRS)


def support(row, solvents):
    return tuple(s for s in solvents if row[f"frac_{s}"] > 0)


def pair_mixtures():
    """Each forbidden pair alone, with every possible third solvent, and with the partner at the 5 uL minimum."""
    out = []
    for pair in FORBIDDEN_PAIRS:
        a, b = sorted(pair)
        out += [{a: .5, b: .5}, {a: 295 / 300, b: 5 / 300}]
        out += [{a: 1 / 3, b: 1 / 3, x: 1 / 3} for x in GREEN_SOLVENTS if x not in pair]
    return out


def test_is_allowed_matches_the_rule_for_every_subset():
    assert any(has_pair(c) for c in SUBSETS)
    assert all(is_allowed(c) != has_pair(c) for c in SUBSETS)
    assert all(is_allowed(c) == is_allowed(c[::-1]) for c in SUBSETS)
    assert not is_allowed(GREEN_SOLVENTS)  # more than three solvents: still caught


def test_sdl_bo_search_space_drops_exactly_the_forbidden_supports():
    from SDL_BO import space
    supports = {tuple(s for s, v in zip(GREEN_SOLVENTS, row) if v > 0) for row in space.enumerate_mixtures(step_ul=50)}
    assert not any(has_pair(s) for s in supports)
    assert {c for c in SUBSETS if not has_pair(c)} == supports


def test_bo_bridge_grid_has_no_forbidden_pair(tmp_path):
    result = run_bridge("grid", "--round", FIRST_ROUND, "-o", tmp_path / "g.csv")
    assert result.returncode == 0, result.stdout + result.stderr
    grid = pd.read_csv(tmp_path / "g.csv")
    assert not any(has_pair(support(row, GREEN_SOLVENTS)) for _, row in grid.iterrows())


@pytest.mark.parametrize("mixture", pair_mixtures(), ids=lambda m: "+".join(m))
def test_bo_bridge_layout_refuses_any_mixture_with_a_pair(tmp_path, mixture):
    suggestions = tmp_path / "s.csv"
    pd.DataFrame([{"condition_id": "X0", **{f"frac_{s}": mixture.get(s, 0.0) for s in GREEN_SOLVENTS}}]).to_csv(suggestions, index=False)
    result = run_bridge("layout", "--round", FIRST_ROUND, "--suggestions", suggestions, "--outdir", tmp_path / "out")
    assert result.returncode != 0 and not (tmp_path / "out" / f"ot_input_round{FIRST_ROUND}.csv").exists()


def test_toy_generator_avoids_pairs():
    import sys
    sys.path.insert(0, str(DEBUG_DIR))
    import make_toy_run
    rng = np.random.default_rng(0)
    assert not any(has_pair(make_toy_run.random_mixture(rng, n)) for n in (2, 3) for _ in range(500))
