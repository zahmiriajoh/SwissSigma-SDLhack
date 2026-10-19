"""Plain-text summary of a campaign: best mixture, best single solvent, and the Pareto front."""
import numpy as np
import pandas as pd

from . import space
from .history import load_history, ratio_columns, score_mixtures

N_PARETO_ROWS_SHOWN = 10


def describe_mixture(mixture_key) -> str:
    """Human-readable composition, e.g. '47.5% acetone + 50% EtOH + 2.5% water'."""
    parts = [f"{units * 100 / space.GRID_STEPS:g}% {solvent}"
             for solvent, units in zip(space.GREEN_SOLVENTS, mixture_key) if units > 0]
    return " + ".join(parts)


def is_pure_solvent(mixture_key) -> bool:
    """True if the mixture has a single solvent."""
    return sum(units > 0 for units in mixture_key) == 1


def _is_dominated(ratios: np.ndarray, this_one: np.ndarray) -> bool:
    """True if some mixture is at least as good on every solute and better on at least one."""
    at_least_as_good = (ratios >= this_one).all(axis=1)
    better_somewhere = (ratios > this_one).any(axis=1)
    return bool((at_least_as_good & better_somewhere).any())


def pareto_front(mixtures: pd.DataFrame) -> pd.DataFrame:
    """Mixtures (from score_mixtures) that no other mixture beats on every solute's ratio_<solute>."""
    ratios = mixtures[ratio_columns(mixtures)].to_numpy()
    return mixtures[[not _is_dominated(ratios, this_one) for this_one in ratios]]


def _best_lines(mixtures: pd.DataFrame) -> list:
    position = int(np.argmax(mixtures["score"].to_numpy()))
    row = mixtures.iloc[position]  # by position: the index holds tuples, which pandas reads as multi-axis labels
    return [f"Best mixture: {describe_mixture(mixtures.index[position])}  "
            f"score={row['score']:.3f} (n={int(row['n'])})"]


def _pure_solvent_lines(mixtures: pd.DataFrame) -> list:
    pure = mixtures.iloc[[i for i, key in enumerate(mixtures.index) if is_pure_solvent(key)]]
    if pure.empty:
        return []
    position = int(np.argmax(pure["score"].to_numpy()))
    lines = [f"Best pure solvent: {describe_mixture(pure.index[position])}  "
             f"score={pure['score'].iloc[position]:.3f}"]
    for column in ratio_columns(mixtures):
        lines.append(f"  {column}: best pure={pure[column].max():.3g}  best overall={mixtures[column].max():.3g}")
    return lines


def _pareto_lines(mixtures: pd.DataFrame) -> list:
    front = pareto_front(mixtures)
    lines = [f"Pareto front: {len(front)} of {len(mixtures)} mixtures are not beaten on every solute"]
    for key, row in front.sort_values("score", ascending=False).head(N_PARETO_ROWS_SHOWN).iterrows():
        ratios = "  ".join(f"{column}={row[column]:.3g}" for column in ratio_columns(mixtures))
        lines.append(f"  {describe_mixture(key)}  score={row['score']:.3f}  {ratios}")
    return lines


def make_report(history_path) -> str:
    """Summarize the history file as text."""
    mixtures = score_mixtures(load_history(history_path))
    footer = ("(ratio_<solute> = absorbance relative to the DMF control on the same plate; "
              "score = the worst solute's ratio; 1.0 = DMF parity)")
    return "\n".join([*_best_lines(mixtures), *_pure_solvent_lines(mixtures), *_pareto_lines(mixtures), footer])
