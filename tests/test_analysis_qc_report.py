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
from production.config import FIRST_PLATE, FIRST_ROUND, SOLUTES
from production.config import is_allowed as config_is_allowed

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
    assert condition_kind("R0_DMFref", 0) == "control"
    assert condition_kind("R0_grid05", 0) == "seed" and condition_kind("R1_seed05", 1) == "seed"
    assert condition_kind("R1_exploit03", 1) == "exploit" and condition_kind("R2_explore00", 2) == "explore"
    assert condition_kind("R0_seed03", 2) == "retest"


def test_qc_layout_fills_the_plate_with_calibration_and_blanks():
    pm = read_plate_map(OT_EXAMPLES / f"plate_map_round{FIRST_ROUND}.csv")
    qc = qc_plate_map(pm)
    from itertools import combinations
    green = [c[len("frac_"):] for c in pm.columns if c.startswith("frac_") and c != "frac_DMF"]
    n_blanks = 7 + sum(config_is_allowed(c) for n in (2, 3) for c in combinations(green, n))  # pure + allowed binaries/ternaries
    assert qc["role"].value_counts().to_dict() == {"calibration": 56, "blank": n_blanks} and len(qc) == 56 + n_blanks <= 96
    vol = qc[[c for c in qc.columns if c.startswith("vol_")]].sum(axis=1)
    assert (vol == 300).all()  # every well gets the full volume
    cols = [c for c in qc.columns if c.startswith("frac_")]
    assert all(config_is_allowed([c[len("frac_"):] for c in cols if row[c] > 0]) for _, row in qc.iterrows())
    pure_blanks = qc[(qc["role"] == "blank") & (qc["solvent"] != "")]
    assert sorted(pure_blanks["solvent"]) == sorted(["DMF", "acetone", "EtOH", "iPrOH", "water", "iPrOAc", "tBuOAc"])
    robot = robot_csv(qc)
    assert list(robot.columns[:3]) == ["well", "solute", "condition_id"] and (robot["solute"] != "").all()


def test_synthetic_blank_reproduces_pure_solvent_wells():
    pm = read_plate_map(OT_EXAMPLES / f"plate_map_round{FIRST_ROUND}.csv")
    qc_map = pd.read_csv(DEBUG_DIR / f"qc_plate_map_round{FIRST_ROUND}.csv", index_col="well")
    qc = read_spectra(DEBUG_DIR / f"reader_round{FIRST_ROUND}_qc.csv")
    blank = synthetic_blank(qc, qc_map, pm)
    assert list(blank.columns) == list(pm.index)
    dmf_blank_well = qc_map.index[(qc_map["role"] == "blank") & (qc_map["solvent"] == "DMF")][0]
    assert np.allclose(blank["A1"], qc[dmf_blank_well])  # A1 is a pure-DMF control: its blank is the DMF blank well


def test_qc_summary_recovers_the_fake_data(toy_run, tmp_path):
    outdir = tmp_path / "figs"
    summary = run_qc(toy_run, outdir).read_text()
    for q in ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"):
        assert f"## {q}" in summary
    r0, p0 = FIRST_ROUND, FIRST_PLATE
    assert (outdir / f"qc_Q7_calibration_round{r0}.png").exists() and (outdir / f"qc_Q4_peakshift_round{r0}.png").exists()
    # the second solute saturates (band 2.6 > 2.5) only in its DMF control well; the last is near the noise
    pm = toy_run.plate_maps[r0]
    ctrl = pm.index[(pm["solute"] == SOLUTES[1]) & (pm["role"] == "control")][0]
    assert f"P{p0}:{ctrl}" in summary and f"P{p0}:A2" not in summary
    # acetone's fake cut-off (330 nm) hides the first solute's 275 nm band: read on the shoulder, flagged not measurable
    report = pd.read_csv(toy_run.folder / f"wavelengths_round{r0}.csv", index_col=0)
    assert report.loc[SOLUTES[0], "wavelength_nm"] >= 330 and not report.loc[SOLUTES[0], "at_band_max"] and not report.loc[SOLUTES[0], "measurable"]
    assert report.loc[SOLUTES[3], "at_band_max"] and abs(report.loc[SOLUTES[3], "wavelength_nm"] - 410) <= 5 and report.loc[SOLUTES[3], "measurable"]
    assert (report["window_min_nm"] >= 330).all()
    # the plate log gives the read-delay panel its data
    plates = {str(p) for p in range(p0, p0 + 3)} | {"qc"}
    assert toy_run.plate_log() is not None and set(toy_run.plate_log()["plate"].astype(str)) >= plates


def test_toy_run_has_no_forbidden_pairs(toy_run):
    s = toy_run.samples()
    cols = [f"frac_{x}" for x in toy_run.green_solvents]
    assert all(config_is_allowed([c[len("frac_"):] for c in cols if row[c] > 0]) for _, row in s.iterrows())


def test_report_finds_the_synergistic_optimum(toy_run, tmp_path):
    outdir = tmp_path / "figs"
    summary = run_report(toy_run, outdir, with_gp=False).read_text()
    assert toy_run.unmeasurable == [SOLUTES[0]] and SOLUTES[0] not in toy_run.measurable_solutes  # hidden under acetone's cut-off
    assert "excluded as NOT measurable" in summary and SOLUTES[0] in summary
    syn = synergy_table(toy_run)
    assert (syn.groupby("solute")["synergy"].mean() > 0).all()
    assert {"synergy_err", "z", "significant"} <= set(syn.columns) and syn["significant"].any()
    assert (syn.loc[syn["significant"], "z"].abs() > 2).all()
    obj = toy_run.pooled_objective().sort_values("obj_min_rel", ascending=False)
    assert set(c[len("rel_"):] for c in obj.columns if c.startswith("rel_")) == set(toy_run.measurable_solutes)
    assert obj.iloc[0]["n_solvents"] > 1  # the toy chemistry rewards balanced mixtures: a mixture tops the measurable objective
    assert obj["obj_min_rel"].max() > obj.loc[obj["n_solvents"] == 1, "obj_min_rel"].max()
    for name in ("R1_per_solute", "R2_objective", "R3_progress", "R4_ternary", "R4_binaries", "R5_synergy", "R6_solutes", "R7_dataset"):
        assert (outdir / f"report_{name}.png").exists()
    assert BAND_HEIGHTS[SOLUTES[1]] > 2.5 and BAND_HEIGHTS[SOLUTES[3]] < 0.1  # the toy really does span the reader's range


def test_cli_qc_layout(tmp_path):
    result = subprocess.run([sys.executable, "-m", "analysis", "qc-layout", "--plate-map", OT_EXAMPLES / f"plate_map_round{FIRST_ROUND}.csv",
                             "--outdir", tmp_path], capture_output=True, text=True, cwd=REPO)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / f"qc_plate_map_round{FIRST_ROUND}.csv").exists() and (tmp_path / f"ot_input_round{FIRST_ROUND}_qc.csv").exists()


def test_run_reads_the_production_csvs_layout_and_skips_unmeasured_rounds(toy_run, tmp_path):
    """Files split into csvs/ratios (robot inputs) and csvs/uvvis (reader exports) with the next round already laid out."""
    import shutil
    csvs = tmp_path / "csvs"
    (csvs / "ratios").mkdir(parents=True)
    (csvs / "uvvis").mkdir()
    for f in toy_run.folder.iterdir():
        if f.suffix != ".csv":
            continue
        sub = "ratios" if f.name.startswith(("plate_map", "qc_plate_map", "ot_input", "suggestions")) else \
              "uvvis" if f.name.startswith(("reader_", "plate_log")) else ""
        shutil.copy(f, csvs / sub / f.name)
    last = max(toy_run.rounds)
    shutil.copy(csvs / "ratios" / f"plate_map_round{last}.csv", csvs / "ratios" / f"plate_map_round{last + 1}.csv")  # laid out, unmeasured
    run = Run(csvs)
    assert run.rounds == toy_run.rounds and run.pending_rounds == [last + 1]
    assert run.wavelengths(last) is not None and run.qc_spectra(last) is not None and run.plate_log() is not None
    assert run.pooled_objective().shape == toy_run.pooled_objective().shape
