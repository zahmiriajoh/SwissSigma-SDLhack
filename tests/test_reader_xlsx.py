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
from conftest import DEBUG_DIR, REPO
from production.config import FIRST_ROUND
from production.convert_reader_xlsx import convert_round, read_xlsx

R = FIRST_ROUND


@pytest.fixture
def spectra():
    return read_spectra(DEBUG_DIR / f"reader_round{R}_plate0.csv")  # wavelength x well


def reader_rows(spectra, as_text=False):
    """The reader's layout: instrument rows, a 'Wavel.' header, one row per well (optionally numbers as decimal-comma text)."""
    fmt = (lambda v: f"{v:.6f}".replace(".", ",")) if as_text else float
    return ([["Absorbance scan"], ["User: lab"], [], ["Wavel."] + [int(w) for w in spectra.index]]
            + [[w] + [fmt(v) for v in spectra[w]] for w in spectra.columns])


def write_xlsx(rows, path):
    pd.DataFrame(rows).to_excel(path, header=False, index=False)
    return path


def as_wide(long):
    return long.pivot(index="wavelength_nm", columns="well", values="absorbance")


@pytest.mark.parametrize("as_text", [False, True], ids=["numbers", "decimal-comma text"])
def test_reader_layout_with_instrument_rows(spectra, tmp_path, as_text):
    got = as_wide(read_xlsx(write_xlsx(reader_rows(spectra, as_text), tmp_path / "r.xlsx")))[spectra.columns]
    assert np.allclose(got.to_numpy(), spectra.to_numpy(), atol=1e-6) and list(got.index) == list(spectra.index)


def test_wells_across_layout(spectra, tmp_path):
    rows = [["Wavelength"] + list(spectra.columns)] + [[nm] + list(spectra.loc[nm]) for nm in spectra.index]
    got = as_wide(read_xlsx(write_xlsx(rows, tmp_path / "r.xlsx")))[spectra.columns]
    assert np.allclose(got.to_numpy(), spectra.to_numpy())


def test_non_numeric_reading_names_the_well(spectra, tmp_path):
    rows = reader_rows(spectra)
    rows[5][3] = "OVER"  # second well row
    with pytest.raises(SpectraError, match=spectra.columns[1]):
        read_xlsx(write_xlsx(rows, tmp_path / "r.xlsx"))


def test_convert_round_writes_csv_and_keeps_a_newer_one(spectra, tmp_path):
    xlsx = write_xlsx(reader_rows(spectra), tmp_path / f"reader_round{R}_plate0.xlsx")
    write_xlsx(reader_rows(spectra), tmp_path / f"reader_round{R + 1}_plate0.xlsx")  # another round: left alone
    assert convert_round(tmp_path, R) == [xlsx.with_suffix(".csv")]
    assert np.allclose(read_spectra(xlsx.with_suffix(".csv"))[spectra.columns].to_numpy(), spectra.to_numpy())
    assert convert_round(tmp_path, R) == []  # the .csv is now at least as new


def test_run_bo_takes_xlsx_from_uvvis(tmp_path):
    csvs = tmp_path / "csvs"
    shutil.copytree(REPO / "production" / "csvs", csvs)
    plate_map = pd.read_csv(csvs / "ratios" / f"plate_map_round{R}.csv").set_index("well")
    rng = np.random.default_rng(0)
    for name, long in [*((f"plate{p}", fpr.spectra_export(plate_map, rng)) for p in range(3)),
                       ("solvents", fpr.solvent_blank_export(rng, round_=R))]:
        write_xlsx(reader_rows(as_wide(long)), csvs / "uvvis" / f"reader_round{R}_{name}.xlsx")
    env = {**os.environ, "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}"}
    result = subprocess.run(["bash", str(REPO / "production" / "run_bo.sh"), str(csvs), "--no-figures"],
                            capture_output=True, text=True, cwd=REPO, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"converted reader_round{R}_solvents.xlsx" in result.stdout
    assert (csvs / "ratios" / f"ot_input_round{R + 1}.csv").exists()
    assert (pd.read_csv(csvs / f"results_round{R}_wells.csv")["abs_blank"] > 0).all()  # the blank workbook was used
