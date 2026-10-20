import numpy as np
import pandas as pd
import pytest

from SDL_BO import dataset, space
from conftest import SDL_BO_EXAMPLES


def make_rows(round_=1, **overrides):
    """Minimal bo_dataset.csv rows: a DMF reference and one 50/50 mixture, for every solute."""
    zero = {c: 0.0 for c in space.FRACTION_COLUMNS}
    rows = []
    for solute in ("S1", "S2"):
        ref = dict(round=round_, solute=solute, condition_id="R1_DMFref", is_reference=1, rel_mean=1.0, **zero)
        ref["frac_DMF"] = 1.0
        mix = dict(round=round_, solute=solute, condition_id="R1_seed01", is_reference=0, rel_mean=0.5, **zero)
        mix.update({"frac_2MeTHF": 0.5, "frac_EtOAc": 0.5, **overrides})
        rows += [ref, mix]
    return pd.DataFrame(rows)


def write(tmp_path, df):
    path = tmp_path / "bo_dataset.csv"
    df.to_csv(path, index=False)
    return path


def test_load_example_dataset_drops_references_and_adds_keys():
    df = dataset.load_dataset(SDL_BO_EXAMPLES / "bo_dataset.csv")
    assert (df["is_reference"] == 0).all()
    assert df["mixture_key"].map(sum).eq(space.TOTAL_UL).all()
    assert dataset.solutes(df) == ["S1", "S2", "S3", "S4"]
    assert dataset.next_round_number(df) == 4


def test_score_is_worst_solute_and_nan_when_incomplete(tmp_path):
    rows = make_rows()
    rows.loc[(rows.solute == "S2") & (rows.is_reference == 0), "rel_mean"] = 0.2
    extra = rows[(rows.solute == "S1") & (rows.is_reference == 0)].copy()  # a condition S2 never saw
    extra["condition_id"], extra["frac_2MeTHF"], extra["frac_EtOAc"] = "R1_seed02", 1.0, 0.0
    scored = dataset.score_mixtures(dataset.load_dataset(write(tmp_path, pd.concat([rows, extra]))))
    assert scored.loc[[(150, 150, 0, 0, 0, 0)], "score"].item() == pytest.approx(0.2)
    assert np.isnan(scored.loc[[(300, 0, 0, 0, 0, 0)], "score"].item())


def test_repeats_across_rounds_are_averaged(tmp_path):
    r2 = make_rows(round_=2, rel_mean=0.7)
    df = dataset.load_dataset(write(tmp_path, pd.concat([make_rows(), r2])))
    scored = dataset.score_mixtures(df)
    assert scored["n"].item() == 2 and scored["score"].item() == pytest.approx(0.6)


@pytest.mark.parametrize("bad, message", [
    (dict(frac_EtOAc=0.6), "sum to 1"),
    (dict(frac_EtOAc=0.0, frac_DMF=0.5), "reference rows"),
    (dict(frac_2MeTHF=0.501, frac_EtOAc=0.499), "whole uL"),
    (dict(frac_2MeTHF=0.25, frac_EtOAc=0.25, frac_DMC=0.25, frac_CPME=0.25), "at most 3"),
])
def test_malformed_rows_are_refused(tmp_path, bad, message):
    with pytest.raises(dataset.DatasetError, match=message):
        dataset.load_dataset(write(tmp_path, make_rows(**bad)))


def test_missing_column_and_missing_rel_mean(tmp_path):
    with pytest.raises(dataset.DatasetError, match="missing columns"):
        dataset.load_dataset(write(tmp_path, make_rows().drop(columns="rel_mean")))
    rows = make_rows()
    rows.loc[rows.is_reference == 0, "rel_mean"] = np.nan
    with pytest.raises(dataset.DatasetError, match="no condition has a rel_mean"):
        with pytest.warns(UserWarning, match="dropping"):
            dataset.load_dataset(write(tmp_path, rows))
