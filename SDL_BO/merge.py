"""Adding one round's measured wells (history format, see history.py; must include its DMF controls) to the history file."""
import os
import shutil
import warnings
from pathlib import Path

import pandas as pd

from .history import HistoryError, absorbance_columns, prepare_history


class MergeError(ValueError):
    """The new round cannot be added to the history."""


def _check_usable(table: pd.DataFrame, what: str) -> None:
    """Raise MergeError unless `table` would load as a history (same checks as load_history)."""
    try:
        prepare_history(table)
    except HistoryError as error:
        raise MergeError(f"{what} would not be usable: {error}") from error


def _write_atomically(table: pd.DataFrame, path: Path) -> None:
    """Write via a temp file so a crash leaves no half-written file; an existing file keeps its permissions."""
    temp_path = path.with_name(path.name + ".tmp")
    try:
        table.to_csv(temp_path, index=False)
        if path.exists():
            shutil.copymode(path, temp_path)
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _check_single_round(round_rows: pd.DataFrame) -> int:
    """Return the round number, or raise MergeError unless `round_rows` holds exactly one round."""
    if "round" not in round_rows.columns:
        raise MergeError("the new data has no 'round' column")
    rounds = sorted(round_rows["round"].unique()) if len(round_rows) else []
    if len(rounds) != 1:
        raise MergeError(f"the new data must contain exactly one round, found {rounds}")
    return rounds[0]


def _combine_with_history(history_path: Path, round_rows: pd.DataFrame, round_number) -> pd.DataFrame:
    """History plus the new round, or MergeError if the round repeats or its solutes differ."""
    existing = pd.read_csv(history_path)
    if round_number in set(existing["round"]):
        raise MergeError(f"round {round_number} is already in {history_path}; refusing to add it twice")
    old_solutes, new_solutes = set(absorbance_columns(existing)), set(absorbance_columns(round_rows))
    if old_solutes != new_solutes:
        raise MergeError(f"solute columns differ: history has {sorted(old_solutes)}, "
                         f"new data has {sorted(new_solutes)}")
    combined = pd.concat([existing, round_rows], ignore_index=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # warnings were already shown for the round alone
        _check_usable(combined, "the history with this round added")
    return combined


def append_round_to_history(history_path, round_rows: pd.DataFrame) -> pd.DataFrame:
    """Append one round's wells to the history file and return the combined table; changes nothing on any MergeError."""
    history_path = Path(history_path)
    round_number = _check_single_round(round_rows)
    _check_usable(round_rows, "the new round")  # on its own first, so errors refer to lines of the round file
    if history_path.exists():
        combined = _combine_with_history(history_path, round_rows, round_number)
    else:
        combined = round_rows.reset_index(drop=True)
    _write_atomically(combined, history_path)
    return combined
