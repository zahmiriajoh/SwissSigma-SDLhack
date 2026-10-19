"""Designing each round (one plate of 32 designs, each measured in triplicate); all state lives in the history file.

    round 1:    1 DMF control + 6 pure green solvents + 25 space-filling mixtures
    round 2+:   1 DMF control + 5 re-tests (highest score so far) + 16 exploit + 10 explore

Output: one row per design (round, the 7 solvent fractions, `type` = a ROW_TYPE_* constant).
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import space
from .history import (absorbance_columns, load_history, next_round_number, ratio_columns,
                      score_mixtures, score_wells)
from .model import fit_gp_per_solute, pick_exploit_batch, pick_explore_batch

# Plate composition from round 2 on; round 1 spends the re-test wells on seed designs too.
N_RETESTS = 5
N_EXPLOIT = 16
N_EXPLORE = 10
N_ROUND1_GREEN_DESIGNS = N_RETESTS + N_EXPLOIT + N_EXPLORE  # 31 non-control designs, including the 6 pure solvents

# Values of the `type` column in the candidates CSV.
ROW_TYPE_SEED = "seed"
ROW_TYPE_EXPLOIT = "bo_exploit"
ROW_TYPE_EXPLORE = "bo_explore"
ROW_TYPE_RETEST = "retest"
ROW_TYPE_CONTROL = "reference"


def _design_rows(green_grid_units, round_number, row_type) -> pd.DataFrame:
    """Turn mixtures (integer grid units over the green solvents) into candidate-CSV rows."""
    green_grid_units = np.asarray(green_grid_units).reshape(-1, len(space.GREEN_SOLVENTS))  # allows an empty selection
    rows = pd.DataFrame(np.round(space.to_fractions(green_grid_units), 6), columns=space.GREEN_SOLVENTS)  # rounding drops float noise
    rows[space.REFERENCE_SOLVENT] = 0.0
    rows["round"] = round_number
    rows["type"] = row_type
    return rows[["round", *space.ALL_SOLVENTS, "type"]]


def _dmf_control_row(round_number) -> pd.DataFrame:
    """One pure-DMF control well for this round."""
    fractions = {solvent: float(solvent == space.REFERENCE_SOLVENT) for solvent in space.ALL_SOLVENTS}
    return pd.DataFrame([{"round": round_number, **fractions, "type": ROW_TYPE_CONTROL}])


def seed_design(n_green_designs=N_ROUND1_GREEN_DESIGNS, round_number=1) -> pd.DataFrame:
    """Round 1: pure solvents, then greedy-maximin mixtures (farthest from all chosen), plus the DMF control. Deterministic."""
    every_mixture = space.enumerate_mixtures()
    n_solvents_used = (every_mixture > 0).sum(axis=1)
    pure_solvents = every_mixture[n_solvents_used == 1]
    mixtures = every_mixture[n_solvents_used > 1]

    # distance from each mixture to the closest design chosen so far
    distance_to_chosen = np.linalg.norm(mixtures[:, None, :] - pure_solvents[None, :, :], axis=2).min(axis=1)
    chosen_mixtures = []
    while len(chosen_mixtures) < n_green_designs - len(pure_solvents):
        farthest = int(np.argmax(distance_to_chosen))
        chosen_mixtures.append(mixtures[farthest])
        distance_to_chosen = np.minimum(distance_to_chosen, np.linalg.norm(mixtures - mixtures[farthest], axis=1))

    designs = np.vstack([pure_solvents, *chosen_mixtures])
    return pd.concat([_design_rows(designs, round_number, ROW_TYPE_SEED), _dmf_control_row(round_number)],
                     ignore_index=True)


@dataclass
class TrainingData:
    """What the models learn from: one row per non-control well (replicates are separate rows)."""

    fractions: np.ndarray    # (n_wells, 6) green-solvent fractions, snapped to the grid
    ratios: np.ndarray       # (n_wells, n_solutes) absorbance / the DMF control of the well's own plate
    mixture_ids: list        # which mixture each well belongs to; replicates share an id
    mixture_keys: set        # the distinct mixtures tested so far


def _training_data(history: pd.DataFrame) -> TrainingData:
    wells = score_wells(history)
    wells = wells[~wells["is_dmf_control"]]
    return TrainingData(
        fractions=space.to_fractions(wells["mixture_key"].tolist()),  # from the keys, so inputs sit exactly on the grid
        ratios=wells[ratio_columns(wells)].to_numpy(),
        mixture_ids=[str(key) for key in wells["mixture_key"]],  # strings: scikit-learn would read tuples as a 2-D array
        mixture_keys=set(wells["mixture_key"]),
    )


def _untested_mixtures(tested_keys: set) -> np.ndarray:
    """Every allowed mixture (integer grid units) that is not in `tested_keys`."""
    all_mixtures = space.enumerate_mixtures()
    return all_mixtures[[space.mixture_key(row) not in tested_keys for row in all_mixtures]]


def _pick_new_mixtures(solute_gps, untested, training, incumbent_score, n_exploit, n_explore, rng):
    """(exploit, explore) indices into `untested`; explore picks avoid the exploit picks."""
    untested_fractions = space.to_fractions(untested)
    exploit = pick_exploit_batch(solute_gps, untested_fractions, n_exploit, incumbent_score, rng)
    remaining = np.setdiff1d(np.arange(len(untested)), exploit)
    measured_or_picked = np.vstack([training.fractions, untested_fractions[exploit]])
    explore = remaining[pick_explore_batch(solute_gps, measured_or_picked, untested_fractions[remaining], n_explore, rng)]
    return exploit, explore


def suggest_next_round(history_path, n_exploit=N_EXPLOIT, n_explore=N_EXPLORE, n_retests=N_RETESTS, seed=0):
    """Design the next round (exploit, explore, re-tests, DMF control); returns (candidates DataFrame, info dict)."""
    history = load_history(history_path)
    round_number = next_round_number(history)
    training = _training_data(history)
    fitted = fit_gp_per_solute(training.fractions, training.ratios, training.mixture_ids, seed=seed)

    untested = _untested_mixtures(training.mixture_keys)
    mixtures_table = score_mixtures(history)  # one row per tested mixture, replicate means
    exploit, explore = _pick_new_mixtures(
        [model.gp for model in fitted], untested, training, mixtures_table["score"].max(),
        n_exploit, n_explore, np.random.default_rng(seed + round_number))
    best_mixtures = np.array(mixtures_table["score"].nlargest(n_retests).index.tolist())

    candidates = pd.concat([
        _design_rows(untested[exploit], round_number, ROW_TYPE_EXPLOIT),
        _design_rows(untested[explore], round_number, ROW_TYPE_EXPLORE),
        _design_rows(best_mixtures, round_number, ROW_TYPE_RETEST),
        _dmf_control_row(round_number),
    ], ignore_index=True)

    solutes = absorbance_columns(history)
    info = {
        "round": round_number,
        "kernels": {solute: model.kernel_name for solute, model in zip(solutes, fitted)},
        "cv_rmse": {solute: model.cv_rmse_by_kernel for solute, model in zip(solutes, fitted)},
        "n_training_wells": len(training.ratios),
    }
    return candidates, info
