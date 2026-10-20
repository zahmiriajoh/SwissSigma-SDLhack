import numpy as np
import pandas as pd
import pytest

from SDL_BO import campaign, dataset, space
from conftest import SDL_BO_EXAMPLES


def solvent_totals_ul(suggestions: pd.DataFrame) -> pd.Series:
    return suggestions[space.GREEN_FRACTION_COLUMNS].sum() * space.TOTAL_UL


def test_seed_design_is_bo_bridge_suggestions_format():
    design = campaign.seed_design()
    assert list(design.columns) == ["condition_id", *space.GREEN_FRACTION_COLUMNS]
    assert len(design) == campaign.N_CONDITIONS
    r, c = space.FIRST_ROUND, space.FIRST_CONDITION
    assert design["condition_id"].tolist()[:2] == [f"R{r}_seed{c:02d}", f"R{r}_seed{c + 1:02d}"]
    fractions = design[space.GREEN_FRACTION_COLUMNS].to_numpy()
    assert np.allclose(fractions.sum(axis=1), 1, atol=5e-4)
    assert (fractions[:6] == np.eye(6)).all()  # pure solvents first
    assert (solvent_totals_ul(design) <= space.solvent_budget_ul() + 1).all()
    assert (space.to_ul(fractions) % space.STEP_UL == 0).all()


def test_seed_design_is_deterministic_and_spread():
    a, b = campaign.seed_design(), campaign.seed_design()
    pd.testing.assert_frame_equal(a, b)
    mixtures = space.to_ul(a[space.GREEN_FRACTION_COLUMNS].to_numpy())
    assert len({space.mixture_key(m) for m in mixtures}) == len(mixtures)


def test_suggest_next_round_from_example_dataset(coarse_grid):
    path = SDL_BO_EXAMPLES / "bo_dataset.csv"
    suggestions, info = campaign.suggest_next_round(path, seed=1)
    tested = set(dataset.load_dataset(path)["mixture_key"])

    this = f"R{space.FIRST_ROUND + 3}_"
    assert info["round"] == space.FIRST_ROUND + 3 and set(info["kernels"]) == set(space.SOLUTES)
    assert len(suggestions) == campaign.N_CONDITIONS
    assert list(suggestions.columns) == ["condition_id", *space.GREEN_FRACTION_COLUMNS]
    assert (solvent_totals_ul(suggestions) <= space.solvent_budget_ul() + 1).all()

    ids = suggestions["condition_id"]
    assert ids.str.startswith(this + "exploit").sum() == campaign.N_EXPLOIT
    assert ids.str.startswith(this + "explore").sum() == campaign.N_EXPLORE
    retests = suggestions[~ids.str.startswith(this)]
    assert len(retests) == campaign.N_RETESTS and retests["condition_id"].str.match(r"R\d+_").all()

    keys = [space.mixture_key(k) for k in space.to_ul(suggestions[space.GREEN_FRACTION_COLUMNS].to_numpy())]
    assert len(set(keys)) == len(keys)
    new = [k for k, i in zip(keys, ids) if i.startswith(this)]
    assert not tested.intersection(new)  # exploit/explore are untested mixtures
    assert all(k in tested for k, i in zip(keys, ids) if not i.startswith(this))  # re-tests are tested ones


def test_suggest_runs_on_a_single_solute(tmp_path, coarse_grid):
    df = pd.read_csv(SDL_BO_EXAMPLES / "bo_dataset.csv")
    path = tmp_path / "bo_dataset.csv"
    df[df.solute == space.SOLUTES[0]].to_csv(path, index=False)
    suggestions, _ = campaign.suggest_next_round(path, seed=0)  # one solute is a valid campaign
    assert len(suggestions) == campaign.N_CONDITIONS
