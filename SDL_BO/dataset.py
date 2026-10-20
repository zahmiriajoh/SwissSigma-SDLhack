"""Reading `bo_dataset.csv` (written by `OT protocols/bo_bridge.py merge`) and scoring mixtures.

One row per round x solute x condition:
    round, solute, condition_id, is_reference, n_solvents, frac_<solvent>..., n_obs, abs_mean, abs_std, rel_mean, rel_std
`rel_mean` is the condition's absorbance relative to the same round's DMF control for that solute, pooled over
all replicate wells and plates. bo_bridge computes it, so this package never sees raw absorbances.

    score of a mixture = the smallest solute's mean rel_mean over every condition row with that composition
A score of 1.0 means "as good as DMF for every solute".
"""
import warnings

import numpy as np
import pandas as pd

from . import space

RATIO_PREFIX = "ratio_"  # ratio_<solute> columns made by ratio_table / score_mixtures
FRACTION_TOLERANCE = 1e-3
REQUIRED_COLUMNS = ["round", "solute", "condition_id", "is_reference", *space.FRACTION_COLUMNS, "rel_mean"]


class DatasetError(ValueError):
    """The dataset has a problem that would silently corrupt the optimization."""


def _csv_lines(df: pd.DataFrame, mask) -> list:
    """CSV line numbers (header = line 1) of the rows selected by `mask`, first 10 only."""
    return [int(i) + 2 for i in df.index[mask]][:10]


def _check_columns(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise DatasetError(f"dataset is missing columns {missing}; expected bo_dataset.csv from bo_bridge.py merge")


def _check_values(df: pd.DataFrame) -> None:
    for column in ["round", "is_reference", "rel_mean", *space.FRACTION_COLUMNS]:
        if not pd.api.types.is_numeric_dtype(df[column]):
            raise DatasetError(f"column '{column}' must be numeric but has non-numeric entries")
    if (df["round"] < 1).any() or (df["round"] != df["round"].round()).any():
        raise DatasetError("'round' must contain positive whole numbers")
    if np.isinf(df["rel_mean"].to_numpy(dtype=float)).any():
        raise DatasetError("rel_mean must be finite (found inf); check the DMF controls")


def _check_fractions(samples: pd.DataFrame) -> None:
    """Non-reference rows: fractions in [0, 1] summing to 1, no DMF, whole uL, few enough solvents."""
    fractions = samples[space.FRACTION_COLUMNS]
    bad_range = (fractions.isna() | (fractions < -FRACTION_TOLERANCE) | (fractions > 1 + FRACTION_TOLERANCE)).any(axis=1)
    if bad_range.any():
        raise DatasetError(f"fractions must be between 0 and 1; CSV lines: {_csv_lines(samples, bad_range)}")
    bad_sum = ~np.isclose(fractions.sum(axis=1), 1.0, atol=FRACTION_TOLERANCE)
    if bad_sum.any():
        raise DatasetError(f"fractions must sum to 1; CSV lines: {_csv_lines(samples, bad_sum)}")
    with_dmf = samples[f"frac_{space.REFERENCE_SOLVENT}"] > FRACTION_TOLERANCE
    if with_dmf.any():
        raise DatasetError(f"{space.REFERENCE_SOLVENT} may only appear in reference rows (is_reference = 1); "
                           f"CSV lines: {_csv_lines(samples, with_dmf)}")
    green_ul = samples[space.GREEN_FRACTION_COLUMNS].to_numpy() * space.TOTAL_UL
    off_grid = ~np.isclose(green_ul, np.rint(green_ul), atol=FRACTION_TOLERANCE * space.TOTAL_UL).all(axis=1)
    if off_grid.any():
        raise DatasetError(f"fractions must be whole uL of {space.TOTAL_UL}; CSV lines: {_csv_lines(samples, off_grid)}")
    too_many = (np.rint(green_ul) > 0).sum(axis=1) > space.MAX_SOLVENTS_PER_MIXTURE
    if too_many.any():
        raise DatasetError(f"mixtures may contain at most {space.MAX_SOLVENTS_PER_MIXTURE} solvents; "
                           f"CSV lines: {_csv_lines(samples, too_many)}")


def validate_dataset(df: pd.DataFrame) -> None:
    """Raise DatasetError if the table is malformed (structure only; missing rel_mean passes)."""
    if len(df) == 0:
        raise DatasetError("the dataset has no rows")
    _check_columns(df)
    _check_values(df)
    samples = df[df["is_reference"] == 0]
    if samples.empty:
        raise DatasetError("the dataset has only DMF reference rows, so there is nothing to optimize yet")
    _check_fractions(samples)


def load_dataset(path) -> pd.DataFrame:
    """Read bo_dataset.csv: validated non-reference rows with a `mixture_key` column; rows without rel_mean are dropped."""
    df = pd.read_csv(path)
    validate_dataset(df)
    samples = df[df["is_reference"] == 0].copy()
    missing = samples["rel_mean"].isna()
    if missing.any():
        warnings.warn(f"dropping {int(missing.sum())} row(s) without rel_mean (no usable DMF control?); "
                      f"CSV lines: {_csv_lines(samples, missing)}")
        samples = samples[~missing]
    if samples.empty:
        raise DatasetError("no condition has a rel_mean value; nothing to learn from")
    negative = samples["rel_mean"] < 0
    if negative.any():
        warnings.warn(f"setting {int(negative.sum())} negative rel_mean value(s) to 0 (blank over-subtraction?)")
        samples["rel_mean"] = samples["rel_mean"].clip(lower=0)
    green_ul = space.to_ul(samples[space.GREEN_FRACTION_COLUMNS].to_numpy())
    samples["mixture_key"] = [space.mixture_key(row) for row in green_ul]
    return samples.reset_index(drop=True)


def solutes(df: pd.DataFrame) -> list:
    return sorted(df["solute"].unique())


def ratio_columns(df: pd.DataFrame) -> list:
    return [c for c in df.columns if c.startswith(RATIO_PREFIX)]


def ratio_table(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (round, condition_id): ratio_<solute> columns (NaN where a solute lacks the condition) + mixture_key."""
    wide = df.pivot_table(index=["round", "condition_id"], columns="solute", values="rel_mean", aggfunc="mean")
    wide.columns = [RATIO_PREFIX + s for s in wide.columns]
    return wide.join(df.groupby(["round", "condition_id"])["mixture_key"].first())


def score_mixtures(df: pd.DataFrame) -> pd.DataFrame:
    """One row per mixture_key: mean ratio_<solute> over its condition rows, `score` (their minimum; NaN if a
    solute never saw the mixture) and `n` condition rows."""
    table = ratio_table(df)
    by_mixture = table.groupby("mixture_key")
    mixtures = by_mixture[ratio_columns(table)].mean()
    mixtures["score"] = mixtures[ratio_columns(table)].min(axis=1, skipna=False)
    mixtures["n"] = by_mixture.size()
    return mixtures


def next_round_number(df: pd.DataFrame) -> int:
    return int(df["round"].max()) + 1
