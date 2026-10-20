"""The toy additive pipeline (SDL_BO -> bo_bridge -> fake spectra -> analysis reduce -> bo_bridge merge) runs and passes."""
import sys

import pandas as pd

from conftest import REPO
from production import config

sys.path.insert(0, str(REPO / "examples"))
import toy_additive_pipeline as toy  # noqa: E402


def test_toy_pipeline_finds_the_dominant_solvent(tmp_path, coarse_grid):
    dominant, r, p = config.GREEN_SOLVENTS[4], config.FIRST_ROUND, config.FIRST_PLATE
    exit_code = toy.main(["--rounds", "1", "--coarse", "--dominant", dominant, "--outdir", str(tmp_path)])
    assert exit_code == 0
    assert (tmp_path / "report.txt").read_text().startswith(f"Best mixture: 100% {dominant} ")
    for name in (f"suggestions_round{r}.csv", f"plate_map_round{r}.csv", f"reader_round{r}_plate{p + 2}.csv",
                 f"reader_round{r}_blank.csv", f"endpoint_round{r}_plate{p}.csv", f"endpoint_round{r}_blank.csv",
                 f"wavelengths_round{r}.csv", f"results_round{r}_wells.csv", "bo_dataset.csv", f"suggestions_round{r + 1}.csv"):
        assert (tmp_path / name).exists(), name
    wavelengths = pd.read_csv(tmp_path / f"wavelengths_round{r}.csv", index_col=0).iloc[:, 0]
    assert all(abs(wavelengths[s] - nm) <= 2 for s, nm in toy.fpr.PEAK_NM.items())  # analysis found the fake bands
