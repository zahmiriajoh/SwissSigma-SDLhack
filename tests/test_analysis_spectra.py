"""analysis: spectra -> endpoint CSVs that bo_bridge merge accepts (uses the synthetic round-1 exports)."""
import subprocess
import sys

import pandas as pd
import pytest

from conftest import DEBUG_DIR, OT_EXAMPLES, REPO
from production.config import FIRST_PLATE, FIRST_ROUND, SOLUTES
from analysis.spectra import SOLVENT_WELLS, SpectraError, predicted_blank, read_plate_map, read_spectra, reduce_round

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


def test_predicted_blank_matches_the_full_blank_plate(blank, plate_map):
    solvents = read_spectra(EXAMPLES / f"reader_round{R}_solvents.csv")
    predicted = predicted_blank(solvents, plate_map)
    assert list(SOLVENT_WELLS.values()) == ["A1", "B1", "C1", "D1", "E1", "F1", "G1"]
    assert list(predicted.columns) == list(plate_map.index) and predicted.shape == blank.shape
    assert (predicted - blank[predicted.columns]).abs().to_numpy().max() < 0.03  # reader noise of one well plus the weighted sum
    pure = predicted[plate_map.index[plate_map["frac_DMF"] == 1]]
    assert (pure.sub(solvents["A1"], axis=0).abs() < 1e-9).all().all()  # a DMF control well's blank is the DMF well


def test_reduce_with_predicted_blank_agrees_with_full_blank(plates, blank, plate_map):
    predicted = predicted_blank(read_spectra(EXAMPLES / f"reader_round{R}_solvents.csv"), plate_map)
    wl_full, ep_full, *_ = reduce_round(plate_map, plates, blank)
    wl_pred, ep_pred, *_ = reduce_round(plate_map, plates, predicted)
    assert (wl_full == wl_pred).all() and len(ep_pred) == 4
    assert (ep_pred[-1]["absorbance"] - ep_full[-1]["absorbance"]).abs().max() < 0.03  # the blank endpoint merge subtracts


def test_solvent_blank_file_must_have_every_solvent_well(plate_map, tmp_path):
    solvents = read_spectra(EXAMPLES / f"reader_round{R}_solvents.csv").drop(columns="G1")
    with pytest.raises(SpectraError, match="G1"):
        predicted_blank(solvents, plate_map)


def test_earlier_round_wavelengths_are_reused_unless_overridden(tmp_path):
    from analysis.cli import _earlier_wavelengths
    for k, nm in ((0, 275.0), (1, 280.0)):
        pd.DataFrame({"wavelength_nm": [nm, None]}, index=pd.Index(["A", "B"], name="solute")).to_csv(tmp_path / f"wavelengths_round{k}.csv")
    assert _earlier_wavelengths(tmp_path, 0) == (None, {})
    assert _earlier_wavelengths(tmp_path, 2) == (1, {"A": 280.0})  # the latest earlier round; unset (NaN) solutes are skipped
