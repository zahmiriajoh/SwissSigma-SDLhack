"""run_bo.sh through round 0 -> 2 on fake reader workbooks: the two arms really diverge after the shared seed round."""
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import fake_plate_reader as fpr
from conftest import REPO
from production.config import ARMS, GREEN_SOLVENTS, N_PLATES, SOLUTES, is_allowed

FRACTIONS = [f"frac_{s}" for s in GREEN_SOLVENTS]
N_CONDITIONS = 23


def run_bo(csvs):
    env = {**os.environ, "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}"}  # the venv's python
    result = subprocess.run(["bash", str(REPO / "production" / "run_bo.sh"), str(csvs), "--no-figures"],
                            capture_output=True, text=True, cwd=REPO, env=env)
    assert result.returncode == 0, result.stdout + result.stderr


def read_round(csvs, r):
    fpr.write_plate_reader_xlsx(fpr.solvent_blank_export(np.random.default_rng(100 + r), round_=r), csvs / "uvvis" / f"reader_round{r}_solvents.xlsx")
    plate_map = pd.read_csv(csvs / "ratios" / f"plate_map_round{r}.csv")
    rng = np.random.default_rng(r + 1)
    for p in range(N_PLATES):
        fpr.write_plate_reader_xlsx(fpr.spectra_export(plate_map.set_index("well"), rng), csvs / "uvvis" / f"reader_round{r}_plate{p}.xlsx")


@pytest.fixture(scope="module")
def campaign(tmp_path_factory):
    csvs = tmp_path_factory.mktemp("branched") / "csvs"
    run_bo(csvs)  # round 0 seed design
    for r in (0, 1):
        read_round(csvs, r)
        run_bo(csvs)  # merge round r, design round r + 1
    return csvs


def conditions(csvs, r):
    plate_map = pd.read_csv(csvs / "ratios" / f"plate_map_round{r}.csv")
    samples = plate_map[plate_map["role"] == "sample"]
    return plate_map, {s: samples.loc[samples["solute"] == s, "condition_id"].tolist() for s in SOLUTES}


def test_round_0_is_shared_and_later_rounds_split_by_arm(campaign):
    _, shared = conditions(campaign, 0)
    assert len({tuple(v) for v in shared.values()}) == 1 and len(shared[SOLUTES[0]]) == N_CONDITIONS
    for r in (1, 2):
        _, per = conditions(campaign, r)
        assert all(len(v) == N_CONDITIONS for v in per.values())
        for arm_solutes in ARMS.values():
            assert len({tuple(per[s]) for s in arm_solutes}) == 1  # an arm's solutes share its conditions
        assert tuple(per[ARMS["phthalimide"][0]]) != tuple(per[ARMS["others"][0]])


def test_each_arms_new_conditions_carry_its_name(campaign):
    for r in (1, 2):
        _, per = conditions(campaign, r)
        for arm, arm_solutes in ARMS.items():
            fresh = [c for c in per[arm_solutes[0]] if c.startswith(f"R{r}_")]
            assert len(fresh) >= 20 and all(c.startswith(f"R{r}_{arm}_") for c in fresh)


def test_no_round_has_a_forbidden_pair(campaign):
    for r in (0, 1, 2):
        plate_map, _ = conditions(campaign, r)
        samples = plate_map[plate_map["role"] == "sample"]
        assert all(is_allowed([s for s, f in zip(GREEN_SOLVENTS, row[FRACTIONS]) if f > 1e-9]) for _, row in samples.iterrows())


def test_each_arm_learns_only_from_its_own_wells(campaign):
    dataset = pd.read_csv(campaign / "bo_dataset.csv")
    samples = dataset[(dataset["is_reference"] == 0) & (dataset["round"] == 1)]
    for arm, arm_solutes in ARMS.items():
        ids = set(samples.loc[samples["solute"].isin(arm_solutes), "condition_id"])
        assert all(i.startswith(f"R1_{arm}_") or not i.startswith("R1_") for i in ids)  # its own picks, or re-tests of earlier ones


def test_blank_is_subtracted_from_the_solvent_wells(campaign):
    wells = pd.read_csv(campaign / "results_round1_wells.csv")
    assert (wells["abs_blank"] > 0).all() and np.allclose(wells["abs_corrected"], wells["abs_raw"] - wells["abs_blank"], atol=1e-3)


def test_wavelengths_picked_in_round_0_are_reused_in_round_1(campaign):
    picked = pd.read_csv(campaign / "wavelengths_round0.csv", index_col=0)["wavelength_nm"]
    assert pd.read_csv(campaign / "wavelengths_round1.csv", index_col=0)["wavelength_nm"].equals(picked)
