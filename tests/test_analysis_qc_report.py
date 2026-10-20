"""analysis qc / report / qc-layout on a fake 2-round campaign built by analysis/examples/make_toy_run.py."""
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from conftest import DEBUG_DIR, OT_EXAMPLES, REPO
from analysis.qc import run_qc
from analysis.qc_layout import qc_plate_map, robot_csv
from analysis.report import run_report, synergy_table
from analysis.run import Run, condition_kind
from analysis.spectra import read_plate_map, read_spectra, synthetic_blank

sys.path.insert(0, str(DEBUG_DIR))
from make_toy_run import BAND_HEIGHTS  # noqa: E402


@pytest.fixture(scope="module")
def toy_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("toy")
    result = subprocess.run([sys.executable, str(DEBUG_DIR / "make_toy_run.py"), "--outdir", out, "--rounds", "2"],
                            capture_output=True, text=True, cwd=REPO)
    assert result.returncode == 0, result.stdout + result.stderr
    return Run(out)


def test_condition_kind_parsing():
    assert condition_kind("R1_DMFref", 1) == "control"
    assert condition_kind("R1_grid05", 1) == "seed" and condition_kind("R1_seed05", 1) == "seed"
    assert condition_kind("R2_exploit03", 2) == "exploit" and condition_kind("R2_explore01", 2) == "explore"
    assert condition_kind("R1_seed03", 3) == "retest"


def test_qc_layout_fills_the_plate_with_calibration_and_blanks():
    pm = read_plate_map(OT_EXAMPLES / "plate_map_round1.csv")
    qc = qc_plate_map(pm)
    assert len(qc) == 96 and qc["role"].value_counts().to_dict() == {"calibration": 56, "blank": 40}
    vol = qc[[c for c in qc.columns if c.startswith("vol_")]].sum(axis=1)
    assert (vol == 300).all()  # every well gets the full volume
    pure_blanks = qc[(qc["role"] == "blank") & (qc["solvent"] != "")]
    assert sorted(pure_blanks["solvent"]) == sorted(["DMF", "2MeTHF", "EtOAc", "DMC", "CPME", "MeCN", "iPrOAc"])
    robot = robot_csv(qc)
    assert list(robot.columns[:3]) == ["well", "solute", "condition_id"] and (robot["solute"] != "").all()


def test_synthetic_blank_reproduces_pure_solvent_wells():
    pm = read_plate_map(OT_EXAMPLES / "plate_map_round1.csv")
    qc_map = pd.read_csv(DEBUG_DIR / "qc_plate_map_round1.csv", index_col="well")
    qc = read_spectra(DEBUG_DIR / "reader_round1_qc.csv")
    blank = synthetic_blank(qc, qc_map, pm)
    assert list(blank.columns) == list(pm.index)
    dmf_blank_well = qc_map.index[(qc_map["role"] == "blank") & (qc_map["solvent"] == "DMF")][0]
    assert np.allclose(blank["A1"], qc[dmf_blank_well])  # A1 is a pure-DMF control: its blank is the DMF blank well


def test_qc_summary_recovers_the_fake_data(toy_run, tmp_path):
    outdir = tmp_path / "figs"
    summary = run_qc(toy_run, outdir).read_text()
    for q in ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"):
        assert f"## {q}" in summary
    assert (outdir / "qc_Q7_calibration_round1.png").exists() and (outdir / "qc_Q4_peakshift_round1.png").exists()
    # S1 saturates (band 2.6 > 2.5) only in its DMF control well A1; S4 is near the noise
    assert "P1:A1" in summary and "P1:A2" not in summary
    wl = toy_run.wavelengths(1)
    assert abs(wl["S1"] - 275) <= 2 and abs(wl["S4"] - 410) <= 5
    # the plate log gives the read-delay panel its data
    assert toy_run.plate_log() is not None and set(toy_run.plate_log()["plate"].astype(str)) >= {"1", "2", "3", "qc"}


def test_report_finds_the_synergistic_optimum(toy_run, tmp_path):
    outdir = tmp_path / "figs"
    summary = run_report(toy_run, outdir, with_gp=False).read_text()
    assert "a mixture beats every single solvent" in summary  # the toy chemistry rewards balanced mixtures
    syn = synergy_table(toy_run)
    assert (syn.groupby("solute")["synergy"].mean() > 0).all()
    obj = toy_run.pooled_objective()
    assert obj["obj_min_rel"].max() > obj.loc[obj["n_solvents"] == 1, "obj_min_rel"].max()
    for name in ("R1_per_solute", "R2_objective", "R3_progress", "R4_ternary", "R4_binaries", "R5_synergy", "R6_solutes", "R7_dataset"):
        assert (outdir / f"report_{name}.png").exists()
    assert BAND_HEIGHTS["S1"] > 2.5  # the toy really does span the reader's range


def test_cli_qc_layout(tmp_path):
    result = subprocess.run([sys.executable, "-m", "analysis", "qc-layout", "--plate-map", OT_EXAMPLES / "plate_map_round1.csv",
                             "--outdir", tmp_path], capture_output=True, text=True, cwd=REPO)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "qc_plate_map_round1.csv").exists() and (tmp_path / "ot_input_round1_qc.csv").exists()
