"""analysis: spectra -> endpoint CSVs that bo_bridge merge accepts (uses the synthetic round-1 exports)."""
import subprocess
import sys

import pandas as pd
import pytest

from conftest import DEBUG_DIR, OT_EXAMPLES, REPO
from production.config import FIRST_PLATE, FIRST_ROUND, SOLUTES
from analysis.spectra import SpectraError, read_plate_map, read_spectra, reduce_round

EXAMPLES = DEBUG_DIR
R = FIRST_ROUND
PLATES = range(FIRST_PLATE, FIRST_PLATE + 3)
PLATE_MAP = OT_EXAMPLES / f"plate_map_round{R}.csv"
TRUE_PEAKS = dict(zip(SOLUTES, [275, 350, 295, 410]))  # fake_plate_reader.PEAK_NM


@pytest.fixture(scope="module")
def plates():
    return [read_spectra(EXAMPLES / f"reader_round{R}_plate{i}.csv") for i in PLATES]


@pytest.fixture(scope="module")
def blank():
    return read_spectra(EXAMPLES / f"reader_round{R}_blank.csv")


@pytest.fixture(scope="module")
def plate_map():
    return read_plate_map(PLATE_MAP)


def test_read_spectra_long_and_wide_agree(plates, tmp_path):
    wide = plates[0].copy()
    wide.columns = [f"{c[0]}{int(c[1:]):02d}" for c in wide.columns]  # zero-padded well names
    wide.to_csv(tmp_path / "wide.csv")
    assert read_spectra(tmp_path / "wide.csv").equals(plates[0])


def test_picked_wavelengths_hit_the_fake_peaks(plates, blank, plate_map):
    wavelengths, endpoints, _, report = reduce_round(plate_map, plates, blank)
    for solute, nm in TRUE_PEAKS.items():
        assert abs(wavelengths[solute] - nm) <= 2
    assert len(endpoints) == 4 and all(len(e) == 96 for e in endpoints)
    assert list(endpoints[0].columns)[:2] == ["well", "absorbance"] and (endpoints[0]["flag"] == "").all()
    assert report["at_band_max"].all() and (report["signal_fraction"] > 0.99).all()


def test_override_wins_and_missing_control_is_an_error(plates, plate_map):
    wavelengths, _, _, _ = reduce_round(plate_map, plates[:1], overrides={SOLUTES[1]: 300})
    assert wavelengths[SOLUTES[1]] == 300
    no_controls = plate_map[plate_map["role"] != "control"]
    with pytest.raises(SpectraError, match="no DMF control"):
        reduce_round(no_controls, plates[:1])


def test_missing_well_is_an_error(plates, plate_map):
    with pytest.raises(SpectraError, match="B5"):
        reduce_round(plate_map, [plates[0].drop(columns=["B5"])])


def test_cli_output_feeds_bo_bridge_merge(tmp_path):
    def run(*args):
        result = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, cwd=REPO)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    out = run("-m", "analysis", "reduce", "--plate-map", PLATE_MAP,
              "--reader", *(EXAMPLES / f"reader_round{R}_plate{i}.csv" for i in PLATES),
              "--blank", EXAMPLES / f"reader_round{R}_blank.csv", "--outdir", tmp_path)
    line = next(l for l in out.splitlines() if SOLUTES[0] in l)
    assert "275 nm (band maximum" in line
    run(REPO / "OT protocols" / "bo_bridge.py", "merge", "--plate-map", PLATE_MAP,
        "--reader", *(tmp_path / f"endpoint_round{R}_plate{i}.csv" for i in PLATES),
        "--blank", tmp_path / f"endpoint_round{R}_blank.csv",
        "--dataset", tmp_path / "bo_dataset.csv", "--wells-out", tmp_path / "wells.csv")
    dataset = pd.read_csv(tmp_path / "bo_dataset.csv")
    controls = dataset[dataset["is_reference"] == 1]
    assert len(dataset) == 96 and (controls["rel_mean"] == 1.0).all()
    assert (dataset.loc[dataset["is_reference"] == 0, "rel_mean"] < 1.0).all()
