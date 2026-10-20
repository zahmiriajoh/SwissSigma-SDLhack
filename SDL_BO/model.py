"""A Gaussian process (GP) per solute, and the two ways we pick new mixtures from them.

* One GP per solute predicts its ratio to DMF from the six green-solvent fractions; the kernel is chosen by cross-validation.
* A mixture's score is its worst solute. "Exploit" picks use batch expected improvement (qEI) to beat the best score so far;
  "explore" picks take the mixtures the models are least sure about.

Notation: fractions (n_rows, 6) model input; targets (n_rows,) rel_mean = absorbance / DMF absorbance;
candidates (n_candidates, 6) the mixtures we choose among.
"""
import warnings
from dataclasses import dataclass

import numpy as np
from scipy.linalg import solve_triangular
from sklearn.exceptions import ConvergenceWarning
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, Matern, WhiteKernel
from sklearn.model_selection import GroupKFold

MIN_USEFUL_GAIN = 1e-10  # an exploit pick must add at least this much expected improvement, or it is random
MIN_EXPLORE_UNCERTAINTY = 1e-4  # posterior / prior variance averaged over solutes (0 = known, 1 = no information)
MIN_VARIANCE = 1e-12  # floor so rounding error never gives a negative variance
JITTER = 1e-8  # added to the picks' covariance diagonal for a stable Cholesky
MIN_IMPROVEMENT = 0.01  # a sample must beat the incumbent score by this much to count as an improvement
N_SAMPLES = 256  # joint GP samples used to estimate expected improvement
MIN_MIXTURES_FOR_CROSS_VALIDATION = 8
N_CROSS_VALIDATION_FOLDS = 5
LENGTH_SCALE_BOUNDS = (0.05, 5.0)  # in volume-fraction units (inputs run 0-1)
FALLBACK_KERNEL = "matern25-iso"  # used when there is too little data to compare kernels


# --------------------------------------------------------------------------------------------
# Fitting one GP per solute
# --------------------------------------------------------------------------------------------
@dataclass
class FittedModel:
    """A fitted GP plus how it was chosen."""

    gp: GaussianProcessRegressor
    kernel_name: str
    cv_rmse_by_kernel: dict  # {kernel name: cross-validated RMSE}; empty if CV was skipped


def _shape_kernel(shape: str, length_scale):
    if shape == "rbf":
        return RBF(length_scale, LENGTH_SCALE_BOUNDS)
    return Matern(length_scale, LENGTH_SCALE_BOUNDS, nu={"matern15": 1.5, "matern25": 2.5}[shape])


def candidate_kernels(n_inputs: int) -> dict:
    """Kernels to compare: amplitude * shape + noise, shape in {matern15, matern25, rbf}, length scale "iso" or "ard" (per solvent)."""
    kernels = {}
    for scale_name, initial_scale in {"iso": 0.5, "ard": np.full(n_inputs, 0.5)}.items():
        for shape in ("matern15", "matern25", "rbf"):
            amplitude = ConstantKernel(1.0, (1e-2, 1e2))
            noise = WhiteKernel(noise_level=1e-2, noise_level_bounds=(1e-5, 1.0))
            kernels[f"{shape}-{scale_name}"] = amplitude * _shape_kernel(shape, initial_scale) + noise
    return kernels


def _signal_kernel(gp):
    """The noise-free part of a fitted GP's kernel (our kernels are `signal + WhiteKernel`)."""
    return gp.kernel_.k1


def _fit_gp(kernel, fractions, targets, n_restarts=3, seed=0):
    gp = GaussianProcessRegressor(
        kernel,
        normalize_y=True,  # the kernel amplitude lives on the standardized scale
        n_restarts_optimizer=n_restarts,
        random_state=seed,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)  # a hyperparameter ending on its bound is normal here
        return gp.fit(fractions, targets)


def _cv_rmse(kernel, fractions, targets, folds, seed) -> float:
    """Cross-validated RMSE of `kernel`; no restarts, since this runs 6 kernels x 5 folds x n_solutes times."""
    squared_errors = []
    for train_rows, test_rows in folds:
        fold_gp = _fit_gp(kernel, fractions[train_rows], targets[train_rows], n_restarts=0, seed=seed)
        squared_errors.append(np.mean((fold_gp.predict(fractions[test_rows]) - targets[test_rows]) ** 2))
    return float(np.sqrt(np.mean(squared_errors)))


def fit_best_gp(fractions, targets, mixture_ids, seed=0) -> FittedModel:
    """Fit the kernel with the lowest CV error (replicates share a fold); FALLBACK_KERNEL if too few mixtures."""
    kernels = candidate_kernels(fractions.shape[1])
    n_mixtures = len(set(mixture_ids))
    if n_mixtures < MIN_MIXTURES_FOR_CROSS_VALIDATION:
        gp = _fit_gp(kernels[FALLBACK_KERNEL], fractions, targets, seed=seed)
        return FittedModel(gp, FALLBACK_KERNEL, {})

    folds = list(GroupKFold(n_splits=min(N_CROSS_VALIDATION_FOLDS, n_mixtures))
                 .split(fractions, targets, mixture_ids))
    cv_rmse_by_kernel = {name: _cv_rmse(kernel, fractions, targets, folds, seed) for name, kernel in kernels.items()}
    best_kernel_name = min(cv_rmse_by_kernel, key=cv_rmse_by_kernel.get)
    gp = _fit_gp(kernels[best_kernel_name], fractions, targets, seed=seed)  # refit on all data, with restarts
    return FittedModel(gp, best_kernel_name, cv_rmse_by_kernel)



# --------------------------------------------------------------------------------------------
# Posterior of the underlying (noise-free) function
# --------------------------------------------------------------------------------------------
class LatentPosterior:
    """A GP's belief about the noise-free ratio at `points` (`mean`, `variance`: (n_points,)), with cross-point covariances.

    Relies on scikit-learn internals (kernel_.k1, _y_train_mean/_std); tests/test_sdl_bo.py checks them.
    """

    def __init__(self, gp, points):
        self.points = points
        self.signal_kernel = _signal_kernel(gp)
        self._target_std = float(np.squeeze(gp._y_train_std))
        target_mean = float(np.squeeze(gp._y_train_mean))

        cross_covariance = self.signal_kernel(gp.X_train_, points)  # (n_train, n_points), standardized units
        # whitening by the Cholesky factor L of (K + noise): cov(a, b) = k(a, b) - (L^-1 k_a)^T (L^-1 k_b)
        self._whitened_cross = solve_triangular(gp.L_, cross_covariance, lower=True)

        self.mean = target_mean + self._target_std * (cross_covariance.T @ gp.alpha_)
        prior_variance = self.signal_kernel.diag(points)
        explained_variance = (self._whitened_cross ** 2).sum(axis=0)
        self.variance = np.maximum(self._target_std ** 2 * (prior_variance - explained_variance), MIN_VARIANCE)

    def covariance_with(self, indices) -> np.ndarray:
        """Posterior covariance between every point and the points at `indices`: (n_points, len(indices))."""
        prior_covariance = self.signal_kernel(self.points, self.points[indices])
        explained_covariance = self._whitened_cross.T @ self._whitened_cross[:, indices]
        return self._target_std ** 2 * (prior_covariance - explained_covariance)


# --------------------------------------------------------------------------------------------
# Picking new mixtures
# --------------------------------------------------------------------------------------------
class Budget:
    """Per-solvent volume still available this round; a pick spends its cost and may rule out later candidates."""

    def __init__(self, remaining_ul):
        self.remaining = np.asarray(remaining_ul, dtype=float).copy()

    def fits(self, cost_ul) -> np.ndarray:
        """Boolean mask over rows of `cost_ul` (n, n_solvents): True where every solvent still fits."""
        return (np.asarray(cost_ul) <= self.remaining + 1e-9).all(axis=1)

    def spend(self, cost_ul) -> None:
        self.remaining -= np.asarray(cost_ul, dtype=float)


def _no_budget(n_candidates, cost):
    """A budget that never rules anything out, with a zero cost table, for callers without volume limits."""
    return Budget(np.zeros(1)), (np.zeros((n_candidates, 1)) if cost is None else cost)


def _pick_setup(n_picks: int, n_candidates: int, rng):
    """Validated (n_picks capped at n_candidates, rng defaulting to a fixed seed)."""
    if n_picks < 0:
        raise ValueError(f"n_picks must be 0 or more, got {n_picks}")
    return min(n_picks, n_candidates), rng or np.random.default_rng(0)


def _conditional_moments(posterior, picks, standard_normals):
    """Mean (n_samples, n_candidates) and variance (n_candidates,) of one solute's ratio, given sampled values at `picks`."""
    pick_number = len(picks)
    if pick_number == 0:
        return posterior.mean[None, :], posterior.variance
    covariance_with_picks = posterior.covariance_with(picks)  # (n_candidates, pick_number)
    picks_cholesky = np.linalg.cholesky(covariance_with_picks[picks] + JITTER * np.eye(pick_number))
    weights = solve_triangular(picks_cholesky, covariance_with_picks.T, lower=True)  # (pick_number, n_candidates)
    earlier_draws = standard_normals[:pick_number]  # (pick_number, n_samples)
    mean = posterior.mean[None, :] + (weights.T @ earlier_draws).T
    return mean, np.maximum(posterior.variance - (weights ** 2).sum(axis=0), MIN_VARIANCE)


def _sampled_scores(posteriors, picks, standard_normals):
    """Sampled score (worst solute's ratio) of every candidate as the next pick: (n_samples, n_candidates).

    Each solute's ratio is sampled conditionally on the sampled values at the picks made so far.
    """
    pick_number = len(picks)
    scores = np.full((standard_normals.shape[1], len(posteriors[0].mean)), np.inf)
    for solute, posterior in enumerate(posteriors):
        mean, variance = _conditional_moments(posterior, picks, standard_normals[:, :, solute])
        fresh_draw = standard_normals[pick_number, :, solute][:, None]  # (n_samples, 1)
        scores = np.minimum(scores, mean + np.sqrt(variance)[None, :] * fresh_draw)
    return scores


def pick_exploit_batch(solute_gps, candidates, n_picks, incumbent_score, rng=None, cost=None, budget=None,
                       min_improvement=MIN_IMPROVEMENT, n_samples=N_SAMPLES) -> list:
    """Greedy qEI: indices into `candidates` that add most expected improvement over `incumbent_score` (random if none do).

    `cost` (n_candidates, n_solvents) and `budget` (a Budget) limit the batch's solvent use; picking stops early if
    nothing affordable is left.
    """
    n_picks, rng = _pick_setup(n_picks, len(candidates), rng)
    if budget is None:
        budget, cost = _no_budget(len(candidates), cost)
    posteriors = [LatentPosterior(gp, candidates) for gp in solute_gps]

    # standard_normals[k] is the fresh randomness of pick k: every candidate is evaluated as "the next pick" with it
    standard_normals = rng.standard_normal((n_picks, n_samples, len(solute_gps)))

    still_available = np.ones(len(candidates), dtype=bool)
    picks = []
    # per sample: the best improvement achieved by the picks so far
    batch_improvement = np.zeros(n_samples)

    for _ in range(n_picks):
        still_available &= budget.fits(cost)
        if not still_available.any():
            break
        sampled_scores = _sampled_scores(posteriors, picks, standard_normals)  # (n_samples, n_candidates)
        improvement = np.maximum(sampled_scores - incumbent_score - min_improvement, 0.0)
        # gain = average rise of the per-sample best improvement
        new_batch_value = np.maximum(batch_improvement[:, None], improvement).mean(axis=0)
        gain = np.where(still_available, new_batch_value - batch_improvement.mean(), -np.inf)

        best_candidate = int(np.argmax(gain))
        if gain[best_candidate] <= MIN_USEFUL_GAIN:
            best_candidate = int(rng.choice(np.flatnonzero(still_available)))
        picks.append(best_candidate)
        still_available[best_candidate] = False
        budget.spend(cost[best_candidate])
        batch_improvement = np.maximum(batch_improvement, improvement[:, best_candidate])
    return picks


def _average_uncertainty(solute_gps, points, known_fractions) -> np.ndarray:
    """Mean over solutes of posterior / prior variance at `points` given data at `known_fractions`: (n_points,)."""
    total = np.zeros(len(points))
    for gp in solute_gps:
        signal_kernel = _signal_kernel(gp)
        cross = signal_kernel(points, known_fractions)
        known_covariance = gp.kernel_(known_fractions)  # K = signal + noise on the diagonal
        explained = np.einsum("ij,ji->i", cross, np.linalg.solve(known_covariance, cross.T))
        prior_variance = signal_kernel.diag(points)
        total += (prior_variance - explained) / prior_variance
    return total / len(solute_gps)


def pick_explore_batch(solute_gps, fixed_fractions, candidates, n_picks, rng=None, cost=None, budget=None,
                       min_uncertainty=MIN_EXPLORE_UNCERTAINTY) -> list:
    """Indices into `candidates` the models know least about, each treated as measured once picked; leftovers are random.

    `fixed_fractions` = everything already measured or picked this round. `cost`/`budget` as in pick_exploit_batch.
    """
    n_picks, rng = _pick_setup(n_picks, len(candidates), rng)
    if budget is None:
        budget, cost = _no_budget(len(candidates), cost)

    def pick(index):
        picks.append(int(index))
        budget.spend(cost[index])

    known_fractions = fixed_fractions.copy()
    remaining = np.arange(len(candidates))  # indices of candidates not picked yet
    picks = []
    while len(picks) < n_picks:
        remaining = remaining[budget.fits(cost[remaining])]
        if not len(remaining):
            return picks
        uncertainty = _average_uncertainty(solute_gps, candidates[remaining], known_fractions)
        most_uncertain = int(np.argmax(uncertainty))
        if uncertainty[most_uncertain] <= min_uncertainty:
            break  # everything left is already well determined by the data
        pick(remaining[most_uncertain])
        known_fractions = np.vstack([known_fractions, candidates[remaining[most_uncertain]]])
        remaining = np.delete(remaining, most_uncertain)

    while len(picks) < n_picks:  # not enough uncertain candidates: fill with affordable random ones
        affordable = remaining[budget.fits(cost[remaining])]
        if not len(affordable):
            break
        chosen = int(rng.choice(affordable))
        pick(chosen)
        remaining = remaining[remaining != chosen]
    return picks
