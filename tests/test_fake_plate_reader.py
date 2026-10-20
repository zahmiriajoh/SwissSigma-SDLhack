import numpy as np

import fake_plate_reader as fpr
from conftest import OT_EXAMPLES


def test_names_and_dissolution_model():
    assert fpr.ALL_SOLVENTS == ["DMF", "2MeTHF", "EtOAc", "DMC", "CPME", "MeCN", "iPrOAc"]
    dmf = [1, 0, 0, 0, 0, 0, 0]
    assert fpr.dissolved_fraction(dmf, "S1") == 1.0
    pure = fpr.dissolved_fraction([0, 1, 0, 0, 0, 0, 0], "S1")
    binary = fpr.dissolved_fraction([0, .5, 0, .5, 0, 0, 0], "S1")
    assert binary > pure  # the synergy bonus rewards mixtures


def test_exports_follow_bo_bridge_reader_formats():
    plate_map = fpr.read_plate_map(OT_EXAMPLES / "plate_map_round1.csv")
    rng = np.random.default_rng(0)
    spectra = fpr.spectra_export(plate_map, rng)
    assert list(spectra.columns) == ["well", "wavelength_nm", "absorbance"]
    assert len(spectra) == 96 * 601 and spectra["well"].nunique() == 96
    assert spectra["wavelength_nm"].min() == 200 and spectra["wavelength_nm"].max() == 800

    endpoint = fpr.endpoint_export(plate_map, rng)
    assert list(endpoint.columns) == ["well", "absorbance"] and len(endpoint) == 96

    blank = fpr.endpoint_export(plate_map, rng, solids=False)
    assert (endpoint["absorbance"] > blank["absorbance"]).all()  # solids add absorbance everywhere
    control = endpoint[plate_map["role"].to_numpy() == "control"]["absorbance"]
    assert (control > endpoint["absorbance"].median()).all()  # DMF dissolves most
