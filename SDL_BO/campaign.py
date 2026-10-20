"""Designing each round as a bo_bridge suggestions CSV: one row per condition, run on every solute.

    round 1:   the 6 pure green solvents + space-filling mixtures          (N_CONDITIONS rows)
    round 2+:  N_RETESTS re-tests + N_EXPLOIT exploit + N_EXPLORE explore  (N_CONDITIONS rows)

`bo_bridge.py layout` adds the DMF control well itself, so no control row is written. With bo_bridge's default
layout (4 solutes x 24 wells, 1 DMF control each) 23 conditions fit per round, each on 3 identical plates.
"""
import warnings

import numpy as np
import pandas as pd

from . import space
from .dataset import load_dataset, next_round_number, score_mixtures, solutes
from .model import Budget, fit_best_gp, pick_exploit_batch, pick_explore_batch

N_CONDITIONS = 23  # conditions per solute in the default bo_bridge layout
N_RETESTS, N_EXPLOIT, N_EXPLORE = 3, 12, 8
assert N_RETESTS + N_EXPLOIT + N_EXPLORE == N_CONDITIONS


def suggestion_rows(green_ul, condition_ids) -> pd.DataFrame:
    """bo_bridge suggestions rows: condition_id + frac_<green solvent> (4 decimals, as bo_bridge writes them)."""
    green_ul = np.asarray(green_ul).reshape(-1, len(space.GREEN_SOLVENTS))
    rows = pd.DataFrame(space.to_fractions(green_ul).round(4), columns=space.GREEN_FRACTION_COLUMNS)
    rows.insert(0, "condition_id", list(condition_ids))
    return rows


def _ids(round_number, tag, n) -> list:
    return [f"R{round_number}_{tag}{i:02d}" for i in range(1, n + 1)]


def _round_budget(n_solutes=space.N_SOLUTES) -> Budget:
    return Budget(np.full(len(space.GREEN_SOLVENTS), space.solvent_budget_ul(n_solutes)))


def seed_design(n_conditions=N_CONDITIONS, round_number=1, n_solutes=space.N_SOLUTES) -> pd.DataFrame:
    """Round 1: the pure solvents, then greedy-maximin mixtures (each farthest from all chosen) within the solvent
    budget. Deterministic."""
    every_mixture = space.enumerate_mixtures()
    n_used = (every_mixture > 0).sum(axis=1)
    pure, mixtures = every_mixture[n_used == 1], every_mixture[n_used > 1]
    budget = _round_budget(n_solutes)
    budget.spend(pure.sum(axis=0))

    distance_to_chosen = np.linalg.norm(mixtures[:, None, :] - pure[None, :, :], axis=2).min(axis=1)
    chosen = []
    while len(chosen) < n_conditions - len(pure):
        affordable = np.where(budget.fits(mixtures), distance_to_chosen, -np.inf)
        farthest = int(np.argmax(affordable))
        if not np.isfinite(affordable[farthest]):
            break
        chosen.append(mixtures[farthest])
        budget.spend(mixtures[farthest])
        distance_to_chosen = np.minimum(distance_to_chosen, np.linalg.norm(mixtures - mixtures[farthest], axis=1))
    designs = np.vstack([pure, *chosen])[:n_conditions]
    return suggestion_rows(designs, _ids(round_number, "seed", len(designs)))


def fit_per_solute(dataset: pd.DataFrame, seed: int) -> dict:
    """{solute: FittedModel}, each trained on that solute's rows (fractions -> rel_mean); repeats share a CV group."""
    fitted = {}
    for solute, rows in dataset.groupby("solute"):
        fractions = space.to_fractions(np.array(rows["mixture_key"].tolist()))
        fitted[solute] = fit_best_gp(fractions, rows["rel_mean"].to_numpy(), rows["mixture_key"].astype(str).tolist(), seed=seed)
    return fitted


def _untested_mixtures(tested_keys: set) -> np.ndarray:
    every_mixture = space.enumerate_mixtures()
    return every_mixture[[space.mixture_key(row) not in tested_keys for row in every_mixture]]


def _retest_rows(dataset: pd.DataFrame, mixtures: pd.DataFrame, n_retests: int, budget: Budget) -> pd.DataFrame:
    """The best-scoring mixtures so far that fit the budget, keeping the condition_id they were first run under."""
    first_id = dataset.sort_values("round").groupby("mixture_key")["condition_id"].first()
    chosen = []
    for key in mixtures["score"].dropna().sort_values(ascending=False).index:
        if len(chosen) == n_retests:
            break
        if budget.fits(np.array([key]))[0]:
            chosen.append(key)
            budget.spend(np.array(key))
    return suggestion_rows(np.array(chosen).reshape(-1, len(space.GREEN_SOLVENTS)), [first_id[k] for k in chosen])


def suggest_next_round(dataset_path, n_exploit=N_EXPLOIT, n_explore=N_EXPLORE, n_retests=N_RETESTS, seed=0):
    """Design the next round from bo_dataset.csv; returns (suggestions DataFrame, info dict)."""
    dataset = load_dataset(dataset_path)
    round_number = next_round_number(dataset)
    mixtures = score_mixtures(dataset)
    if mixtures["score"].isna().all():
        raise ValueError("no mixture has been measured on every solute, so there is no score to improve on")
    fitted = fit_per_solute(dataset, seed)
    gps = [fitted[s].gp for s in solutes(dataset)]
    rng = np.random.default_rng(seed + round_number)

    budget = _round_budget(len(gps))
    retests = _retest_rows(dataset, mixtures, n_retests, budget)
    untested = _untested_mixtures(set(dataset["mixture_key"]))
    candidates = space.to_fractions(untested)
    exploit = pick_exploit_batch(gps, candidates, n_exploit, mixtures["score"].max(), rng, cost=untested, budget=budget)
    remaining = np.setdiff1d(np.arange(len(untested)), exploit)
    known = np.vstack([space.to_fractions(np.array(mixtures.index.tolist())), candidates[exploit]])
    explore = remaining[pick_explore_batch(gps, known, candidates[remaining], n_explore, rng,
                                           cost=untested[remaining], budget=budget)]

    suggestions = pd.concat([
        retests,
        suggestion_rows(untested[exploit], _ids(round_number, "exploit", len(exploit))),
        suggestion_rows(untested[explore], _ids(round_number, "explore", len(explore))),
    ], ignore_index=True)
    if len(suggestions) < n_retests + n_exploit + n_explore:
        warnings.warn(f"round {round_number}: only {len(suggestions)} conditions fit the solvent budget")
    info = {
        "round": round_number,
        "kernels": {s: m.kernel_name for s, m in fitted.items()},
        "cv_rmse": {s: m.cv_rmse_by_kernel for s, m in fitted.items()},
        "n_training_rows": len(dataset),
        "incumbent_score": float(mixtures["score"].max()),
    }
    return suggestions, info
