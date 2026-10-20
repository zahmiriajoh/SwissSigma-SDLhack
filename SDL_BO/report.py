"""Plain-text summary of a campaign: best mixture, best single solvent, and the Pareto front."""
import numpy as np
import pandas as pd

from . import space
from .dataset import load_dataset, ratio_columns, score_mixtures, unmeasurable_solutes

N_PARETO_ROWS_SHOWN = 10


def describe_mixture(mixture_key) -> str:
    """Human-readable composition, e.g. '50% EtOH + 50% water'."""
    return " + ".join(f"{ul * 100 / space.TOTAL_UL:g}% {solvent}"
                      for solvent, ul in zip(space.GREEN_SOLVENTS, mixture_key) if ul > 0)


def is_pure_solvent(mixture_key) -> bool:
    return sum(ul > 0 for ul in mixture_key) == 1


def _is_dominated(ratios: np.ndarray, this_one: np.ndarray) -> bool:
    """True if some mixture is at least as good on every solute and better on at least one."""
    return bool(((ratios >= this_one).all(axis=1) & (ratios > this_one).any(axis=1)).any())


def pareto_front(mixtures: pd.DataFrame) -> pd.DataFrame:
    """Fully measured mixtures (from score_mixtures) that no other mixture beats on every solute."""
    complete = mixtures.dropna(subset=ratio_columns(mixtures))
    ratios = complete[ratio_columns(complete)].to_numpy()
    return complete[[not _is_dominated(ratios, row) for row in ratios]]


def _best_line(mixtures: pd.DataFrame, label: str) -> str:
    position = int(np.nanargmax(mixtures["score"].to_numpy()))  # by position: the index holds tuples
    row = mixtures.iloc[position]
    return f"{label}: {describe_mixture(mixtures.index[position])}  score={row['score']:.3f} (n={int(row['n'])})"


def _pure_solvent_lines(mixtures: pd.DataFrame) -> list:
    pure = mixtures.iloc[[i for i, key in enumerate(mixtures.index) if is_pure_solvent(key)]]
    if pure["score"].isna().all():
        return []
    lines = [_best_line(pure, "Best pure solvent")]
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


def make_report(dataset_path) -> str:
    """Summarize bo_dataset.csv as text."""
    unmeasurable = unmeasurable_solutes(dataset_path)
    mixtures = score_mixtures(load_dataset(dataset_path), exclude=unmeasurable)
    if mixtures["score"].isna().all():
        return "No mixture has been measured on every solute yet."
    footer = ("(ratio_<solute> = absorbance relative to the DMF control of the same round; "
              "score = the worst solute's ratio; 1.0 = DMF parity)")
    if unmeasurable:
        footer += f"\nNot scored, flagged not measurable by analysis reduce: {', '.join(unmeasurable)}"
    return "\n".join([_best_line(mixtures, "Best mixture"), *_pure_solvent_lines(mixtures), *_pareto_lines(mixtures), footer])
