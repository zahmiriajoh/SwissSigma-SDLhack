"""Reading the history CSV (one row per measured WELL) and turning absorbances into scores (details: HOW_IT_WORKS.md).

    round, DMF, acetone, EtOH, iPrOH, water, iPrOAc, tBuOAc, abs_<solute1>, abs_<solute2>, ...

Solvent columns are intended volume fractions (rows sum to 1); every `abs_` column is one solute; extra columns are ignored.
DMF is a control, never a model input: each well is normalized by the mean pure-DMF absorbance of its own round (plate).

    ratio of a solute in a well = its absorbance / mean DMF-control absorbance of the same round
    score of a mixture          = the smallest solute ratio, after averaging each solute's ratio over the mixture's wells
A score of 1.0 means "as good as DMF for every solute".
"""
import warnings

import numpy as np
import pandas as pd

from . import space

ABSORBANCE_PREFIX = "abs_"
RATIO_PREFIX = "ratio_"  # per-well absorbance divided by the same round's DMF control
RESERVED_COLUMNS = {"score", "is_dmf_control", "mixture_key"}  # added by score_wells, so the input may not use them
FRACTION_TOLERANCE = 1e-3  # how far a recorded fraction may be from the intended grid value


class HistoryError(ValueError):
    """The history file has a problem that would silently corrupt the optimization."""


def _csv_lines(df: pd.DataFrame, mask) -> list:
    """CSV line numbers (header = line 1) of the rows selected by `mask`, first 10 only."""
    return [int(i) + 2 for i in df.index[mask]][:10]


def _columns_with_prefix(df: pd.DataFrame, prefix: str) -> list:
    return [column for column in df.columns if column.startswith(prefix)]


def absorbance_columns(df: pd.DataFrame) -> list:
    """Solute absorbance columns (abs_<solute>)."""
    return _columns_with_prefix(df, ABSORBANCE_PREFIX)


def ratio_columns(df: pd.DataFrame) -> list:
    """Ratio-to-DMF columns added by score_wells / score_mixtures (ratio_<solute>)."""
    return _columns_with_prefix(df, RATIO_PREFIX)


def is_dmf_control(df: pd.DataFrame) -> pd.Series:
    """True for control wells: pure DMF."""
    return (df[space.REFERENCE_SOLVENT] - 1.0).abs() <= FRACTION_TOLERANCE


# --------------------------------------------------------------------------------------------
# Loading and validating
# --------------------------------------------------------------------------------------------
def _check_columns(df: pd.DataFrame) -> None:
    """Required columns exist and no reserved names are used."""
    missing = [c for c in ["round", *space.ALL_SOLVENTS] if c not in df.columns]
    if missing or not absorbance_columns(df):
        raise HistoryError(
            f"history needs columns round, {space.ALL_SOLVENTS} and at least one {ABSORBANCE_PREFIX}<solute> "
            f"column; missing: {missing or 'no abs_ columns'}")
    reserved = [c for c in df.columns if c.startswith(RATIO_PREFIX) or c in RESERVED_COLUMNS]
    if reserved:
        raise HistoryError(f"column name(s) {reserved} are reserved for values this program computes "
                           f"(anything starting with '{RATIO_PREFIX}', and {sorted(RESERVED_COLUMNS)}); please rename them")


def _check_values(df: pd.DataFrame) -> None:
    """Columns are numeric, absorbances are not infinite (missing is allowed), rounds are positive integers."""
    absorbance_cols = absorbance_columns(df)
    for column in ["round", *space.ALL_SOLVENTS, *absorbance_cols]:
        if not pd.api.types.is_numeric_dtype(df[column]):
            raise HistoryError(f"column '{column}' must be numeric but has non-numeric entries")
    if np.isinf(df[absorbance_cols].to_numpy(dtype=float)).any():
        raise HistoryError("absorbances must be finite numbers (found inf); check the reader export")
    if (df["round"] < 1).any() or (df["round"] != df["round"].round()).any():
        raise HistoryError("'round' must contain positive whole numbers")


def _check_fractions(df: pd.DataFrame) -> None:
    """Solvent fractions are between 0 and 1 and sum to 1; DMF is only ever a pure control."""
    fractions = df[space.ALL_SOLVENTS]
    out_of_range = (fractions.isna() | (fractions < -FRACTION_TOLERANCE) | (fractions > 1 + FRACTION_TOLERANCE)).any(axis=1)
    if out_of_range.any():
        raise HistoryError("solvent fractions must be numbers between 0 and 1; "
                           f"CSV lines that are not (header = line 1): {_csv_lines(df, out_of_range)}")
    bad_sums = ~np.isclose(fractions.sum(axis=1), 1.0, atol=FRACTION_TOLERANCE)
    if bad_sums.any():
        raise HistoryError(f"solvent fractions must sum to 1; CSV lines that do not (header = line 1): {_csv_lines(df, bad_sums)}")
    mixed_with_dmf = (df[space.REFERENCE_SOLVENT] > FRACTION_TOLERANCE) & ~is_dmf_control(df)
    if mixed_with_dmf.any():
        raise HistoryError("DMF must only appear as a pure control (DMF = 1), never mixed with other solvents; "
                           f"offending CSV lines (header = line 1): {_csv_lines(df, mixed_with_dmf)}")


def _check_mixtures(df: pd.DataFrame) -> None:
    """There is something to optimize, and every mixture lies on the design grid with few enough solvents."""
    green_units = df.loc[~is_dmf_control(df), space.GREEN_SOLVENTS].to_numpy() * space.GRID_STEPS
    if len(green_units) == 0:
        raise HistoryError("history contains no non-DMF wells, so there is nothing to optimize yet")
    off_grid = ~np.isclose(green_units, np.rint(green_units), atol=FRACTION_TOLERANCE * space.GRID_STEPS)
    if off_grid.any():
        raise HistoryError(f"fractions must be multiples of 1/{space.GRID_STEPS} (the design grid); "
                           "was the history recorded with a different grid?")
    too_many_solvents = (np.rint(green_units) > 0).sum(axis=1) > space.MAX_SOLVENTS_PER_MIXTURE
    if too_many_solvents.any():
        raise HistoryError(f"mixtures may contain at most {space.MAX_SOLVENTS_PER_MIXTURE} solvents")


def validate_history(df: pd.DataFrame) -> None:
    """Raise HistoryError if the table is malformed (structure only; missing absorbances pass)."""
    if len(df) == 0:
        raise HistoryError("the history file has no data rows")
    _check_columns(df)
    _check_values(df)
    _check_fractions(df)
    _check_mixtures(df)


def _drop_wells_with_missing_absorbance(df: pd.DataFrame) -> pd.DataFrame:
    """Drop wells missing any absorbance (for all solutes), with a warning."""
    absorbance_cols = absorbance_columns(df)
    has_missing = df[absorbance_cols].isna().any(axis=1)
    if has_missing.any():
        solutes = [c for c in absorbance_cols if df.loc[has_missing, c].isna().any()]
        warnings.warn(f"dropping {int(has_missing.sum())} well(s) with a missing absorbance reading "
                      f"(missing for: {solutes}); a well is dropped for all solutes")
        df = df[~has_missing].reset_index(drop=True)
    return df


def _zero_negative_absorbances(df: pd.DataFrame) -> pd.DataFrame:
    """Blank subtraction can give slightly negative absorbances."""
    absorbance_cols = absorbance_columns(df)
    negative = (df[absorbance_cols] < 0).any(axis=1)
    if negative.any():
        warnings.warn(f"setting negative absorbances in {int(negative.sum())} well(s) to 0")
        df[absorbance_cols] = df[absorbance_cols].clip(lower=0)
    return df


def prepare_history(df: pd.DataFrame) -> pd.DataFrame:
    """Validate and clean a history table (shared by load_history and merge, so merge accepts only loadable data)."""
    validate_history(df)
    df = df.copy()
    df[space.ALL_SOLVENTS] = df[space.ALL_SOLVENTS].clip(lower=0)  # fractions like -1e-16 are float noise
    cleaned = _zero_negative_absorbances(_drop_wells_with_missing_absorbance(df))
    _check_cleaned(cleaned, dropped_wells=len(cleaned) < len(df))
    return cleaned


def _check_cleaned(df: pd.DataFrame, dropped_wells: bool) -> None:
    """After cleaning there must still be something to optimize and a usable DMF control on every plate."""
    try:
        validate_history(df)
        dmf_reference_by_round(df)
    except HistoryError as error:
        if dropped_wells:
            raise HistoryError(f"{error} (this was checked AFTER dropping wells with missing readings)") from error
        raise


def load_history(path) -> pd.DataFrame:
    """Read the history CSV and prepare it."""
    return prepare_history(pd.read_csv(path))


# --------------------------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------------------------
def dmf_reference_by_round(df: pd.DataFrame) -> pd.DataFrame:
    """Mean DMF-control absorbance per solute and round (index = round); HistoryError if a plate lacks a control or reads zero."""
    absorbance_cols = absorbance_columns(df)
    controls = is_dmf_control(df)
    rounds_with_samples = set(df.loc[~controls, "round"])
    rounds_with_controls = set(df.loc[controls, "round"])
    no_control = sorted(rounds_with_samples - rounds_with_controls)
    if no_control:
        raise HistoryError(f"round(s) {no_control} have no DMF control wells; every plate needs its own control")
    reference = df.loc[controls, absorbance_cols + ["round"]].groupby("round").mean()
    zero = reference.le(0).stack()
    broken = [(int(rnd), column) for rnd, column in zero[zero].index]
    if broken:
        raise HistoryError(f"the DMF control reads zero for (round, solute) {broken}; "
                           "check the control wells before continuing")
    return reference


def ratios_to_dmf(df: pd.DataFrame) -> pd.DataFrame:
    """ratio_<solute> columns: each well's absorbance over its round's DMF-control mean (same index as `df`)."""
    absorbance_cols = absorbance_columns(df)
    reference = dmf_reference_by_round(df).loc[df["round"]]  # one reference row per well
    ratios = df[absorbance_cols].to_numpy() / reference.to_numpy()
    names = [RATIO_PREFIX + column[len(ABSORBANCE_PREFIX):] for column in absorbance_cols]
    return pd.DataFrame(ratios, index=df.index, columns=names)


def score_wells(df: pd.DataFrame) -> pd.DataFrame:
    """Add ratio_<solute>, is_dmf_control, mixture_key and score (the well's worst ratio; noisy, so rank with score_mixtures)."""
    ratios = ratios_to_dmf(df)
    scored = pd.concat([df, ratios], axis=1)
    scored["is_dmf_control"] = is_dmf_control(df)
    scored["score"] = ratios.min(axis=1)
    green_units = space.to_grid_units(df[space.GREEN_SOLVENTS].to_numpy())
    scored["mixture_key"] = [space.mixture_key(row) for row in green_units]
    return scored


def score_mixtures(df: pd.DataFrame) -> pd.DataFrame:
    """One row per tested mixture (controls excluded): mean ratio_<solute>, `score` (their minimum) and `n` wells.

    Ratios are averaged BEFORE taking the minimum: the mean of per-well minimums is biased low by noise.
    """
    wells = score_wells(df)
    wells = wells[~wells["is_dmf_control"]]
    by_mixture = wells.groupby("mixture_key")
    ratio_cols = ratio_columns(wells)
    mixtures = by_mixture[ratio_cols].mean()
    mixtures["score"] = mixtures[ratio_cols].min(axis=1)
    mixtures["n"] = by_mixture.size()
    return mixtures


def next_round_number(df: pd.DataFrame) -> int:
    """The round that comes after the last one in the history."""
    return int(df["round"].max()) + 1
