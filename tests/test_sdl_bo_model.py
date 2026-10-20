import numpy as np
import pytest
from sklearn.gaussian_process import GaussianProcessRegressor

from SDL_BO import model, space


def tiny_fit(seed=0):
    """A GP on a few 6-D points with target = fraction of the first solvent."""
    rng = np.random.default_rng(seed)
    ul = space.enumerate_mixtures(step_ul=100)
    rows = rng.choice(len(ul), 12, replace=False)
    fractions = space.to_fractions(ul[rows])
    targets = fractions[:, 0] + rng.normal(0, 0.01, len(rows))
    return model.fit_best_gp(fractions, targets, [str(r) for r in rows]), fractions


def test_latent_posterior_matches_sklearn_mean_and_noise_free_std():
    fitted, _ = tiny_fit()
    points = space.to_fractions(space.enumerate_mixtures(step_ul=150))
    posterior = model.LatentPosterior(fitted.gp, points)
    mean, std = fitted.gp.predict(points, return_std=True)
    noise = fitted.gp.kernel_.k2.noise_level * fitted.gp._y_train_std ** 2
    assert np.allclose(posterior.mean, mean, atol=1e-6)
    assert np.allclose(posterior.variance, np.maximum(std**2 - noise, model.MIN_VARIANCE), atol=1e-6)


def test_budget_masks_and_spends():
    budget = model.Budget([100, 50])
    cost = np.array([[60, 10], [50, 60], [10, 10]])
    assert budget.fits(cost).tolist() == [True, False, True]
    budget.spend(cost[0])
    assert budget.fits(cost).tolist() == [False, False, True]


def test_exploit_prefers_high_predicted_region_and_respects_budget():
    fitted, _ = tiny_fit()
    candidates_ul = space.enumerate_mixtures(step_ul=50)
    candidates = space.to_fractions(candidates_ul)
    picks = model.pick_exploit_batch([fitted.gp], candidates, 5, incumbent_score=0.5)
    assert len(set(picks)) == 5
    assert candidates[picks[0], 0] > 0.5  # target rises with solvent 0; later picks diversify (qEI)

    budget = model.Budget(np.full(6, 400.0))  # at most ~1.3 wells' worth of any solvent
    picks = model.pick_exploit_batch([fitted.gp], candidates, 10, 0.5, cost=candidates_ul, budget=budget)
    assert len(picks) < 10 and (budget.remaining >= -1e-9).all()
    assert (candidates_ul[picks].sum(axis=0) <= 400).all()


def test_explore_avoids_known_points_and_respects_budget():
    fitted, known = tiny_fit()
    candidates_ul = space.enumerate_mixtures(step_ul=50)
    candidates = space.to_fractions(candidates_ul)
    picks = model.pick_explore_batch([fitted.gp], known, candidates, 4)
    assert len(set(picks)) == 4
    distances = np.linalg.norm(candidates[picks][:, None] - known[None], axis=2).min(axis=1)
    assert (distances > 0.1).all()  # far from the training points

    budget = model.Budget(np.full(6, 300.0))
    picks = model.pick_explore_batch([fitted.gp], known, candidates, 10, cost=candidates_ul, budget=budget)
    assert (candidates_ul[picks].sum(axis=0) <= 300).all()


def test_fallback_kernel_with_few_mixtures():
    fractions = space.to_fractions(space.enumerate_mixtures(step_ul=300))  # 6 pure solvents only
    fitted = model.fit_best_gp(fractions, np.arange(6) / 6, [str(i) for i in range(6)])
    assert isinstance(fitted.gp, GaussianProcessRegressor)
    assert fitted.kernel_name == model.FALLBACK_KERNEL and fitted.cv_rmse_by_kernel == {}


def test_exploit_falls_back_to_best_predicted_when_nothing_can_improve():
    """Incumbent already at the optimum of a confidently known linear target: picks are the highest predicted, not random."""
    ul = space.enumerate_mixtures(step_ul=50)
    fractions = space.to_fractions(ul)
    fitted = model.fit_best_gp(fractions, fractions[:, 0], [str(i) for i in range(len(ul))])  # noise-free, all points
    candidates_ul = space.enumerate_mixtures(step_ul=25)
    candidates = space.to_fractions(candidates_ul)
    picks = model.pick_exploit_batch([fitted.gp], candidates, 6, incumbent_score=1.0)
    assert candidates[picks, 0].min() >= 0.75  # all picks in the solvent-0-rich corner
