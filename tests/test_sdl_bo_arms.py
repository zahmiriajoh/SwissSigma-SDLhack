"""Branched campaign: each arm of production/config.toml is designed from its own solutes' rows only."""
import pandas as pd
import pytest

from SDL_BO import campaign, dataset, space
from conftest import SDL_BO_EXAMPLES, run_bridge
from production import config

ARMS = config.ARMS
PHTH, OTHERS = list(ARMS)
EXAMPLE = SDL_BO_EXAMPLES / "bo_dataset.csv"


def write_dataset(tmp_path, df, name="bo_dataset.csv"):
    path = tmp_path / name
    df.to_csv(path, index=False)
    return path


def test_arms_cover_every_solute_once():
    assert sorted(s for solutes in ARMS.values() for s in solutes) == sorted(config.SOLUTES)
    assert ARMS[PHTH] == ["Phthalimide"] and "Phthalimide" not in ARMS[OTHERS]


def test_config_rejects_a_solute_in_two_arms(tmp_path):
    text = config.CONFIG_PATH.read_text().replace('solutes = ["Phthalimide"]', 'solutes = ["Phthalimide", "Glutarimide"]')
    bad = tmp_path / "config.toml"
    bad.write_text(text)
    with pytest.raises(ValueError, match="exactly one arm"):
        config.load(bad)


def test_arm_ignores_the_other_arms_rows(tmp_path, coarse_grid):
    df = pd.read_csv(EXAMPLE)
    mine = ARMS[PHTH]
    only_mine = write_dataset(tmp_path, df[df.solute.isin(mine)], "only_mine.csv")
    scrambled = df.copy()
    scrambled.loc[~scrambled.solute.isin(mine), "rel_mean"] = 0.123  # the other arm's data must not matter
    all_rows = write_dataset(tmp_path, scrambled, "scrambled.csv")
    a, _ = campaign.suggest_next_round(only_mine, seed=0, arm=PHTH, arm_solutes=mine)
    b, info = campaign.suggest_next_round(all_rows, seed=0, arm=PHTH, arm_solutes=mine)
    pd.testing.assert_frame_equal(a, b)
    assert set(info["kernels"]) == set(mine)  # one GP for the phthalimide arm


def test_others_arm_scores_the_minimum_of_its_three_solutes(coarse_grid):
    _, info = campaign.suggest_next_round(EXAMPLE, seed=0, arm=OTHERS, arm_solutes=ARMS[OTHERS])
    df = dataset.load_dataset(EXAMPLE)
    expected = dataset.score_mixtures(df[df.solute.isin(ARMS[OTHERS])])["score"].max()
    assert set(info["kernels"]) == set(ARMS[OTHERS]) and info["incumbent_score"] == pytest.approx(expected)


def test_suggest_arms_writes_one_table_with_a_solute_column(coarse_grid):
    suggestions, infos = campaign.suggest_arms(EXAMPLE, seed=0)
    n, round_ = campaign.N_CONDITIONS, space.FIRST_ROUND + 3
    assert list(infos) == [PHTH, OTHERS] and list(suggestions.columns) == ["condition_id", *space.GREEN_FRACTION_COLUMNS, "solute"]
    per_solute = {s: suggestions.loc[suggestions.solute == s, "condition_id"].tolist() for s in config.SOLUTES}
    assert all(len(ids) == n for ids in per_solute.values())
    assert len({tuple(per_solute[s]) for s in ARMS[OTHERS]}) == 1  # the three others share their conditions
    new = {a: {i for s in ARMS[a] for i in per_solute[s] if i.startswith(f"R{round_}_")} for a in ARMS}
    assert all(i.startswith(f"R{round_}_{a}_") for a in ARMS for i in new[a]) and not new[PHTH] & new[OTHERS]  # arm-tagged, no collisions


def test_bo_bridge_lays_out_each_arm_on_its_own_blocks(tmp_path, coarse_grid):
    suggestions, _ = campaign.suggest_arms(EXAMPLE, seed=0)
    path = tmp_path / "suggestions.csv"
    suggestions.to_csv(path, index=False)
    result = run_bridge("layout", "--round", space.FIRST_ROUND + 3, "--suggestions", path, "--outdir", tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    plate_map = pd.read_csv(tmp_path / f"plate_map_round{space.FIRST_ROUND + 3}.csv")
    samples = plate_map[plate_map.role == "sample"]
    for solute in config.SOLUTES:
        assert set(samples.loc[samples.solute == solute, "condition_id"]) == set(suggestions.loc[suggestions.solute == solute, "condition_id"])
    assert samples.groupby("solute").condition_id.nunique().eq(campaign.N_CONDITIONS).all()


def test_all_unmeasurable_solutes_are_scored_anyway(tmp_path, coarse_grid):
    df = pd.read_csv(EXAMPLE)
    path = write_dataset(tmp_path, df)
    flagged = pd.DataFrame({"measurable": [False] * len(ARMS[OTHERS])}, index=ARMS[OTHERS])
    flagged.index.name = "solute"
    flagged.to_csv(tmp_path / "wavelengths_round0.csv")
    with pytest.warns(UserWarning, match="scoring them anyway"):
        _, info = campaign.suggest_next_round(path, seed=0, arm=OTHERS, arm_solutes=ARMS[OTHERS])
    assert info["unmeasurable"] == []
    _, info = campaign.suggest_next_round(path, seed=0, arm=PHTH, arm_solutes=ARMS[PHTH])  # a flagged solute elsewhere does not matter
    assert info["unmeasurable"] == []
