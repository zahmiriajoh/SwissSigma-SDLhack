"""analysis qc / report on a fake 2-round campaign built by analysis/examples/make_toy_run.py."""
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from conftest import DEBUG_DIR, REPO
from analysis.qc import run_qc
from analysis.report import run_report, synergy_table
from analysis.run import Run, condition_kind
from analysis.spectra import ABS_MAX_DEFAULT
from production.config import FIRST_PLATE, FIRST_ROUND, SOLUTES
from production.config import is_allowed as config_is_allowed

sys.path.insert(0, str(DEBUG_DIR))
from fake_plate_reader import PEAK_NM  # noqa: E402
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
    assert condition_kind("R1_others_exploit03", 1) == "exploit" and condition_kind("R1_phthalimide_explore01", 1) == "explore"


def test_qc_summary_recovers_the_fake_data(toy_run, tmp_path):
    outdir = tmp_path / "figs"
    summary = run_qc(toy_run, outdir).read_text()
    for q in ("Q1", "Q2", "Q4", "Q5", "Q6"):
        assert f"## {q}" in summary
    r0, p0 = FIRST_ROUND, FIRST_PLATE
    assert (outdir / f"qc_Q4_peakshift_round{r0}.png").exists()
    # the second solute's band (4.5) is over range in its DMF control well: the reader returns OVER = 4.0, which Q4 reports
    pm = toy_run.plate_maps[r0]
    ctrl = pm.index[(pm["solute"] == SOLUTES[1]) & (pm["role"] == "control")][0]
    assert f"P{p0}:{ctrl}" in summary
    # no blanks: each solute is read at its fixed wavelength, and the last (near the noise floor) is still measurable
    report = pd.read_csv(toy_run.folder / f"wavelengths_round{r0}.csv", index_col=0)
    assert report["wavelength_nm"].to_dict() == {s: float(PEAK_NM[s]) for s in SOLUTES}
    assert report.loc[SOLUTES[3], "measurable"]
    # the plate log gives the read-delay panel its data
    plates = {str(p) for p in range(p0, p0 + 3)}
    assert toy_run.plate_log() is not None and set(toy_run.plate_log()["plate"].astype(str)) >= plates


def test_toy_run_has_no_forbidden_pairs(toy_run):
    s = toy_run.samples()
    cols = [f"frac_{x}" for x in toy_run.green_solvents]
    assert all(config_is_allowed([c[len("frac_"):] for c in cols if row[c] > 0]) for _, row in s.iterrows())


def test_report_finds_the_synergistic_optimum(toy_run, tmp_path):
    outdir = tmp_path / "figs"
    summary = run_report(toy_run, outdir, with_gp=False).read_text()
    assert toy_run.unmeasurable == [] and set(toy_run.measurable_solutes) == set(SOLUTES)  # no blanks, so no solute is declared hidden
    assert "excluded as NOT measurable" not in summary
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
    assert BAND_HEIGHTS[SOLUTES[1]] >= ABS_MAX_DEFAULT and BAND_HEIGHTS[SOLUTES[3]] < 0.1  # the toy really spans the reader's range


def test_run_restricted_to_an_arm_has_that_arms_objective(toy_run):
    arm = [SOLUTES[2]]
    one = Run(toy_run.folder, arm).pooled_objective()
    assert [c for c in one.columns if c.startswith("rel_")] == [f"rel_{arm[0]}"] and (one["obj_min_rel"] == one[f"rel_{arm[0]}"]).all()
    pair = [SOLUTES[1], SOLUTES[3]]
    two = Run(toy_run.folder, pair).pooled_objective()
    assert np.allclose(two["obj_min_rel"], two[[f"rel_{s}" for s in pair]].min(axis=1))


def test_run_scores_an_arm_anyway_when_all_its_solutes_are_unmeasurable(toy_run, tmp_path):
    import shutil
    folder = tmp_path / "copy"
    shutil.copytree(toy_run.folder, folder)
    report = pd.read_csv(folder / f"wavelengths_round{FIRST_ROUND}.csv", index_col=0)
    report.loc[SOLUTES[2], "measurable"] = False
    report.to_csv(folder / f"wavelengths_round{FIRST_ROUND}.csv")
    with pytest.warns(UserWarning, match="scoring them anyway"):
        run = Run(folder, [SOLUTES[2]])
    assert run.unmeasurable == [] and run.measurable_solutes == [SOLUTES[2]]


def test_cli_report_arms_writes_one_report_per_arm(toy_run, tmp_path):
    from production.config import ARMS
    result = subprocess.run([sys.executable, "-m", "analysis", "report", "--arms", "--no-gp", "--run", toy_run.folder, "--outdir", tmp_path],
                            capture_output=True, text=True, cwd=REPO)
    assert result.returncode == 0, result.stdout + result.stderr
    assert all((tmp_path / arm / "report_summary.md").exists() for arm in ARMS)


def test_run_reads_the_production_csvs_layout_and_skips_unmeasured_rounds(toy_run, tmp_path):
    """Files split into csvs/ratios (robot inputs) and csvs/uvvis (reader exports) with the next round already laid out."""
    import shutil
    csvs = tmp_path / "csvs"
    (csvs / "ratios").mkdir(parents=True)
    (csvs / "uvvis").mkdir()
    for f in toy_run.folder.iterdir():
        if f.suffix != ".csv":
            continue
        sub = "ratios" if f.name.startswith(("plate_map", "ot_input", "suggestions")) else \
              "uvvis" if f.name.startswith(("reader_", "plate_log")) else ""
        shutil.copy(f, csvs / sub / f.name)
    last = max(toy_run.rounds)
    shutil.copy(csvs / "ratios" / f"plate_map_round{last}.csv", csvs / "ratios" / f"plate_map_round{last + 1}.csv")  # laid out, unmeasured
    run = Run(csvs)
    assert run.rounds == toy_run.rounds and run.pending_rounds == [last + 1]
    assert run.wavelengths(last) is not None and run.plate_log() is not None
    assert run.pooled_objective().shape == toy_run.pooled_objective().shape


def test_figures_so_far_commands_of_run_bo_sh(toy_run, tmp_path):
    """The two commands run_bo.sh's "figures so far" step runs: qc, then report --arms (one report per arm, GP on)."""
    from production.config import ARMS
    fig = tmp_path / "figures"
    for args in (["qc"], ["report", "--arms"]):
        result = subprocess.run([sys.executable, "-m", "analysis", *args, "--run", toy_run.folder, "--outdir", fig],
                                capture_output=True, text=True, cwd=REPO)
        assert result.returncode == 0, result.stdout + result.stderr
    assert (fig / "qc_summary.md").exists()
    for arm, solutes in ARMS.items():
        summary = (fig / arm / "report_summary.md").read_text()
        assert f"arm {arm}" in summary.splitlines()[0] and (fig / arm / "report_R4_gp.png").exists()
        if len(solutes) == 1:
            assert "nothing to compare" in summary and not (fig / arm / "report_R6_solutes.png").exists()


def test_saturation_flag_is_the_readers_over_value():
    """The flag means "the reader returned OVER": the threshold is the converter's capped value, so they cannot drift."""
    from production.convert_reader_xlsx import OVER_ABS
    assert ABS_MAX_DEFAULT == OVER_ABS


def test_saturated_readings_stay_in_the_data_as_real_values(toy_run):
    """User decision: an over-range reading is kept as OVER = 4.0 and used, never dropped; the flag is informational.
    Exactly the readings at 4.0 are flagged, nothing below."""
    r0, p0 = FIRST_ROUND, FIRST_PLATE
    endpoint = pd.read_csv(toy_run.folder / f"endpoint_round{r0}_plate{p0}.csv")
    flagged = endpoint["flag"].fillna("").str.contains("saturated")
    assert flagged.any() and (flagged == (endpoint["absorbance"] >= ABS_MAX_DEFAULT)).all()
    wells = toy_run.wells
    saturated = wells[wells["abs_raw"] >= ABS_MAX_DEFAULT]
    assert len(saturated) and saturated["abs_corrected"].notna().all() and saturated["rel_to_DMF"].notna().all()
