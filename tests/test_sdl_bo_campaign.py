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
    assert design["condition_id"].tolist()[:2] == ["R1_seed01", "R1_seed02"]
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

    assert info["round"] == 4 and set(info["kernels"]) == {"S1", "S2", "S3", "S4"}
    assert len(suggestions) == campaign.N_CONDITIONS
    assert list(suggestions.columns) == ["condition_id", *space.GREEN_FRACTION_COLUMNS]
    assert (solvent_totals_ul(suggestions) <= space.solvent_budget_ul() + 1).all()

    ids = suggestions["condition_id"]
    assert ids.str.startswith("R4_exploit").sum() == campaign.N_EXPLOIT
    assert ids.str.startswith("R4_explore").sum() == campaign.N_EXPLORE
    retests = suggestions[~ids.str.startswith("R4_")]
    assert len(retests) == campaign.N_RETESTS and retests["condition_id"].str.match(r"R\d+_").all()

    keys = [space.mixture_key(k) for k in space.to_ul(suggestions[space.GREEN_FRACTION_COLUMNS].to_numpy())]
    assert len(set(keys)) == len(keys)
    new = [k for k, i in zip(keys, ids) if i.startswith("R4_")]
    assert not tested.intersection(new)  # exploit/explore are untested mixtures
    assert all(k in tested for k, i in zip(keys, ids) if not i.startswith("R4_"))  # re-tests are tested ones


def test_suggest_refuses_dataset_without_complete_mixture(tmp_path, coarse_grid):
    df = pd.read_csv(SDL_BO_EXAMPLES / "bo_dataset.csv")
    only_s1 = df[(df.solute == "S1") | (df.is_reference == 1)]
    only_s1.loc[only_s1.solute == "S2", "rel_mean"] = np.nan
    path = tmp_path / "bo_dataset.csv"
    only_s1[only_s1.solute.isin(["S1"]) | (only_s1.is_reference == 0)].to_csv(path, index=False)
    suggestions, _ = campaign.suggest_next_round(path, seed=0)  # one solute is a valid campaign
    assert len(suggestions) == campaign.N_CONDITIONS
