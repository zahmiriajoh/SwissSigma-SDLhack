import numpy as np

import fake_plate_reader as fpr
from conftest import OT_EXAMPLES
from production import config


def test_names_and_dissolution_model():
    assert fpr.ALL_SOLVENTS == config.ALL_SOLVENTS and list(fpr.PEAK_NM) == config.SOLUTES
    solute = config.SOLUTES[0]
    dmf = [1, 0, 0, 0, 0, 0, 0]
    assert fpr.dissolved_fraction(dmf, solute) == 1.0
    pure = fpr.dissolved_fraction([0, 1, 0, 0, 0, 0, 0], solute)
    binary = fpr.dissolved_fraction([0, .5, 0, .5, 0, 0, 0], solute)
    assert binary > pure  # the synergy bonus rewards mixtures


def test_exports_follow_bo_bridge_reader_formats():
    plate_map = fpr.read_plate_map(OT_EXAMPLES / f"plate_map_round{config.FIRST_ROUND}.csv")
    rng = np.random.default_rng(0)
    spectra = fpr.spectra_export(plate_map, rng)
    assert list(spectra.columns) == ["well", "wavelength_nm", "absorbance"]
    assert len(spectra) == 96 * 101 and spectra["well"].nunique() == 96
    assert spectra["wavelength_nm"].min() == 200 and spectra["wavelength_nm"].max() == 700

    endpoint = fpr.endpoint_export(plate_map, rng)
    assert list(endpoint.columns) == ["well", "absorbance"] and len(endpoint) == 96

    blank = fpr.endpoint_export(plate_map, rng, solids=False)
    assert (endpoint["absorbance"] > blank["absorbance"]).all()  # solids add absorbance everywhere
    control = endpoint[plate_map["role"].to_numpy() == "control"]["absorbance"]
    assert (control > endpoint["absorbance"].median()).all()  # DMF dissolves most


def test_plate_reader_csv_round_trips_through_read_spectra(tmp_path):
    from analysis.spectra import read_spectra
    plate_map = fpr.read_plate_map(OT_EXAMPLES / f"plate_map_round{config.FIRST_ROUND}.csv")
    spectra = fpr.spectra_export(plate_map, np.random.default_rng(0))
    fpr.write_plate_reader_csv(spectra, tmp_path / "plate.csv")
    assert (tmp_path / "plate.csv").read_text().startswith("Wavel.;200;205;")
    wide = read_spectra(tmp_path / "plate.csv")
    assert list(wide.columns) == list(plate_map.index) and wide.index[[0, -1]].tolist() == [200, 700]
    assert np.allclose(wide["A1"].to_numpy(), spectra[spectra["well"] == "A1"]["absorbance"].to_numpy())
