"""The toy additive pipeline (SDL_BO -> bo_bridge -> fake spectra -> analysis reduce -> bo_bridge merge) runs and passes."""
import sys

import pandas as pd

from conftest import REPO

sys.path.insert(0, str(REPO / "examples"))
import toy_additive_pipeline as toy  # noqa: E402


def test_toy_pipeline_finds_the_dominant_solvent(tmp_path, coarse_grid):
    exit_code = toy.main(["--rounds", "1", "--coarse", "--dominant", "MeCN", "--outdir", str(tmp_path)])
    assert exit_code == 0
    assert (tmp_path / "report.txt").read_text().startswith("Best mixture: 100% MeCN ")
    for name in ("suggestions_round1.csv", "plate_map_round1.csv", "reader_round1_plate3.csv", "reader_round1_blank.csv",
                 "endpoint_round1_plate1.csv", "endpoint_round1_blank.csv", "wavelengths_round1.csv",
                 "results_round1_wells.csv", "bo_dataset.csv", "suggestions_round2.csv"):
        assert (tmp_path / name).exists(), name
    wavelengths = pd.read_csv(tmp_path / "wavelengths_round1.csv", index_col=0).iloc[:, 0]
    assert all(abs(wavelengths[s] - nm) <= 2 for s, nm in toy.fpr.PEAK_NM.items())  # analysis found the fake bands
