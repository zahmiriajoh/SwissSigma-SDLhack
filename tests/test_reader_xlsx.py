"""Plate-reader .xlsx workbooks in uvvis/ are converted to the .csv the analysis reads, inside run_bo.sh."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import fake_plate_reader as fpr
from analysis.spectra import SpectraError, read_spectra
from conftest import REPO
from production.config import FIRST_ROUND
from production.convert_reader_xlsx import OVER_ABS, convert_round, read_xlsx

R = FIRST_ROUND


WELL_ROW = 29  # 0-based row of A1 in a Tecan sheet: settings rows 0-27, the 'Wavel.' header in row 28


@pytest.fixture
def long():
    """Fake full-plate spectra (well, wavelength_nm, absorbance) for the committed round-0 plate map."""
    plate_map = pd.read_csv(REPO / "production" / "csvs" / "ratios" / f"plate_map_round{R}.csv").set_index("well")
    return fpr.spectra_export(plate_map, np.random.default_rng(0))


def write_xlsx(rows, path, extra_sheets=()):
    with pd.ExcelWriter(path) as workbook:
        for i, sheet in enumerate([rows, *extra_sheets]):
            pd.DataFrame(sheet).to_excel(workbook, sheet_name=f"Sheet{i + 1}", header=False, index=False)
    return path


def as_wide(long):
    return long.pivot(index="wavelength_nm", columns="well", values="absorbance")


def same(got, long):
    want = as_wide(long)
    return list(got.index) == list(want.index) and np.allclose(got[want.columns].to_numpy(), want.to_numpy(), atol=1e-6)


def test_tecan_workbook_with_an_empty_sheet(long, tmp_path):
    fpr.write_plate_reader_xlsx(long, tmp_path / "r.xlsx")
    assert same(as_wide(read_xlsx(tmp_path / "r.xlsx")), long)


def test_decimal_comma_text_and_any_wavelength_grid(long, tmp_path):
    coarse = long[long["wavelength_nm"].between(230, 698)].assign(wavelength_nm=lambda d: d["wavelength_nm"] - 2)  # 228, 233, ...
    rows = fpr.tecan_rows(coarse)
    rows[WELL_ROW:WELL_ROW + 96] = [[r[0]] + [f"{v:.6f}".replace(".", ",") for v in r[1:]] for r in rows[WELL_ROW:WELL_ROW + 96]]
    assert same(as_wide(read_xlsx(write_xlsx(rows, tmp_path / "r.xlsx"))), coarse)


def test_wells_across_layout(long, tmp_path):
    wide = as_wide(long)
    rows = [["Wavelength"] + list(wide.columns)] + [[nm] + list(wide.loc[nm]) for nm in wide.index]
    assert same(as_wide(read_xlsx(write_xlsx(rows, tmp_path / "r.xlsx"))), long)


def test_several_scans_in_one_workbook_are_refused(long, tmp_path):
    rows = fpr.tecan_rows(long)
    with pytest.raises(SpectraError, match="2 scans.*Sheet1.*Sheet2"):
        read_xlsx(write_xlsx(rows, tmp_path / "r.xlsx", extra_sheets=[rows]))


def test_non_numeric_reading_names_the_well(long, tmp_path):
    rows = fpr.tecan_rows(long)
    rows[WELL_ROW + 1][3] = "n/a"  # second well
    with pytest.raises(SpectraError, match=rows[WELL_ROW + 1][0]):
        read_xlsx(write_xlsx(rows, tmp_path / "r.xlsx"))


@pytest.mark.parametrize("text", ["OVER", "Overflow", ">4.000"])
def test_over_range_reading_is_capped(long, tmp_path, text):
    rows = fpr.tecan_rows(long)
    rows[WELL_ROW + 1][3] = text  # second well, third wavelength
    got = as_wide(read_xlsx(write_xlsx(rows, tmp_path / "r.xlsx")))
    assert got.loc[rows[WELL_ROW - 1][3], rows[WELL_ROW + 1][0]] == OVER_ABS


def test_convert_round_writes_csv_and_keeps_a_newer_one(long, tmp_path):
    xlsx = tmp_path / f"reader_round{R}_plate0.xlsx"
    fpr.write_plate_reader_xlsx(long, xlsx)
    fpr.write_plate_reader_xlsx(long, tmp_path / f"reader_round{R + 1}_plate0.xlsx")  # another round: left alone
    assert convert_round(tmp_path, R) == [xlsx.with_suffix(".csv")]
    assert same(read_spectra(xlsx.with_suffix(".csv")), long)
    assert convert_round(tmp_path, R) == []  # the .csv is now at least as new


def run_bo(csvs, *flags):
    env = {**os.environ, "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}"}
    return subprocess.run(["bash", str(REPO / "production" / "run_bo.sh"), str(csvs), "--no-figures", *flags],
                          capture_output=True, text=True, cwd=REPO, env=env)


def upload_round(tmp_path, solvents=True):
    """A copy of production/csvs with round R's plate workbooks (and the solvent blank plate) in uvvis/."""
    csvs = tmp_path / "csvs"
    shutil.copytree(REPO / "production" / "csvs", csvs)
    plate_map = pd.read_csv(csvs / "ratios" / f"plate_map_round{R}.csv").set_index("well")
    rng = np.random.default_rng(0)
    exports = [(f"plate{p}", fpr.spectra_export(plate_map, rng)) for p in range(3)]
    for name, long in exports + ([("solvents", fpr.solvent_blank_export(rng, round_=R))] if solvents else []):
        fpr.write_plate_reader_xlsx(long, csvs / "uvvis" / f"reader_round{R}_{name}.xlsx")
    return csvs


def test_run_bo_waits_for_the_solvent_blank_plate(tmp_path):
    csvs = upload_round(tmp_path, solvents=False)
    result = run_bo(csvs)
    assert result.returncode == 2 and f"reader_round{R}_solvents.xlsx" in result.stdout
    assert not (csvs / f"results_round{R}_wells.csv").exists()
    assert run_bo(csvs, "--allow-no-blank").returncode == 0


def test_run_bo_takes_xlsx_from_uvvis(tmp_path):
    csvs = upload_round(tmp_path)
    result = run_bo(csvs)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"converted reader_round{R}_solvents.xlsx" in result.stdout
    assert (csvs / "ratios" / f"ot_input_round{R + 1}.csv").exists()
    assert (pd.read_csv(csvs / f"results_round{R}_wells.csv")["abs_blank"] > 0).all()  # the blank workbook was used
