import numpy as np
import pandas as pd
import pytest

from SDL_BO import dataset, space
from conftest import SDL_BO_EXAMPLES

REF = f"frac_{space.REFERENCE_SOLVENT}"
G = space.GREEN_FRACTION_COLUMNS  # G[0], G[1], ... = the green solvents' frac_ columns
SOLUTE_A, SOLUTE_B = space.SOLUTES[:2]


def make_rows(round_=space.FIRST_ROUND, **overrides):
    """Minimal bo_dataset.csv rows: a DMF reference and one 50/50 mixture, for two solutes."""
    zero = {c: 0.0 for c in space.FRACTION_COLUMNS}
    rows = []
    for solute in (SOLUTE_A, SOLUTE_B):
        ref = dict(round=round_, solute=solute, condition_id="R0_DMFref", is_reference=1, rel_mean=1.0, **zero)
        ref[REF] = 1.0
        mix = dict(round=round_, solute=solute, condition_id="R0_seed00", is_reference=0, rel_mean=0.5, **zero)
        mix.update({G[0]: 0.5, G[1]: 0.5, **overrides})
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
    assert dataset.solutes(df) == sorted(space.SOLUTES)
    assert dataset.next_round_number(df) == space.FIRST_ROUND + 3


def test_score_is_worst_solute_and_nan_when_incomplete(tmp_path):
    rows = make_rows()
    rows.loc[(rows.solute == SOLUTE_B) & (rows.is_reference == 0), "rel_mean"] = 0.2
    extra = rows[(rows.solute == SOLUTE_A) & (rows.is_reference == 0)].copy()  # a condition the other solute never saw
    extra["condition_id"], extra[G[0]], extra[G[1]] = "R0_seed01", 1.0, 0.0
    scored = dataset.score_mixtures(dataset.load_dataset(write(tmp_path, pd.concat([rows, extra]))))
    assert scored.loc[[(150, 150, 0, 0, 0, 0)], "score"].item() == pytest.approx(0.2)
    assert np.isnan(scored.loc[[(300, 0, 0, 0, 0, 0)], "score"].item())


def test_repeats_across_rounds_are_averaged(tmp_path):
    r2 = make_rows(round_=space.FIRST_ROUND + 1, rel_mean=0.7)
    df = dataset.load_dataset(write(tmp_path, pd.concat([make_rows(), r2])))
    scored = dataset.score_mixtures(df)
    assert scored["n"].item() == 2 and scored["score"].item() == pytest.approx(0.6)


@pytest.mark.parametrize("bad, message", [
    ({G[1]: 0.6}, "sum to 1"),
    ({G[1]: 0.0, REF: 0.5}, "reference rows"),
    ({G[0]: 0.501, G[1]: 0.499}, "whole uL"),
    ({G[0]: 0.25, G[1]: 0.25, G[2]: 0.25, G[3]: 0.25}, "at most 3"),
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


def test_unmeasurable_solutes_leave_the_score(tmp_path):
    """A solute flagged measurable == False in any round's wavelengths file (from analysis reduce) is not scored."""
    path = write(tmp_path, pd.concat([make_rows(), make_rows(round_=space.FIRST_ROUND + 1, rel_mean=0.7)]))
    flagged = SOLUTE_B
    report = pd.DataFrame({"wavelength_nm": [275, 275], "measurable": [True, False]}, index=pd.Index([SOLUTE_A, flagged], name="solute"))
    report.to_csv(tmp_path / f"wavelengths_round{space.FIRST_ROUND + 1}.csv")
    pd.DataFrame({"wavelength_nm": [275, 275]}, index=report.index).to_csv(tmp_path / f"wavelengths_round{space.FIRST_ROUND}.csv")  # old format, no flag
    assert dataset.unmeasurable_solutes(path) == [flagged]
    df = dataset.load_dataset(path)
    df.loc[df.solute == flagged, "rel_mean"] = 0.01  # noise that must not drive the score
    scored = dataset.score_mixtures(df, exclude=[flagged])
    assert scored["score"].item() == pytest.approx(0.6)  # mean of the measurable solute's 0.5 and 0.7
    with pytest.raises(dataset.DatasetError, match="every solute is excluded"):
        dataset.score_mixtures(df, exclude=[SOLUTE_A, flagged])
