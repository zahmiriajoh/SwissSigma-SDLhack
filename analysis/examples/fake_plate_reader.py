"""Fake plate reader: synthetic absorbance data for a plate map written by `OT protocols/bo_bridge.py layout`.

Solvent and solute names mirror bo_bridge.py. Each solute has one Gaussian absorption band whose height
scales with a made-up "dissolved fraction" that rewards balanced mixtures, so a mixture can beat every
pure solvent as the project hypothesis predicts. Debugging only: none of the numbers are real.
"""
import numpy as np
import pandas as pd

GREEN_SOLVENTS = ["2MeTHF", "EtOAc", "DMC", "CPME", "MeCN", "iPrOAc"]
ALL_SOLVENTS = ["DMF"] + GREEN_SOLVENTS
FRACTION_COLUMNS = [f"frac_{s}" for s in ALL_SOLVENTS]
WAVELENGTHS = np.arange(200, 801)  # nm, 1 nm steps
PEAK_NM = {"S1": 275, "S2": 320, "S3": 350, "S4": 410}  # band centre per solute
WIDTH_NM = {"S1": 18, "S2": 22, "S3": 25, "S4": 35}
BAND_HEIGHT = 1.2  # peak absorbance of a fully dissolved solute
BAND_HEIGHTS = {}  # per-solute override of BAND_HEIGHT, e.g. {"S1": 2.6} to saturate, {"S4": 0.06} to sit near the noise
ATTACK_PER_MIN = {}  # solvent -> absorbance gained per minute of contact at 300 nm (polystyrene attack); default none
NOISE = 0.004
READER_MAX = 3.5  # the reader cannot report more than this absorbance
SYNERGY = 0.4  # bonus for balanced mixtures: 0 for a pure solvent, up to SYNERGY * 2/3 for an equal ternary

# Made-up dissolving power (0-1) of each solvent for each solute; DMF dissolves everything.
POWER = pd.DataFrame(
    {"S1": [1, .7, .4, .6, .5, .3, .4], "S2": [1, .3, .6, .5, .2, .7, .4],
     "S3": [1, .5, .3, .4, .7, .6, .3], "S4": [1, .4, .5, .6, .3, .5, .7]},
    index=ALL_SOLVENTS,
)


def read_plate_map(path) -> pd.DataFrame:
    """A bo_bridge plate map indexed by well, in plate order."""
    return pd.read_csv(path, index_col="well")


def dissolved_fraction(fractions, solute) -> float:
    """Fraction-weighted dissolving power plus a synergy bonus, capped at 1 (fully dissolved)."""
    fractions = np.asarray(fractions, dtype=float)
    return min(fractions @ POWER[solute].to_numpy() + SYNERGY * (1 - np.sum(fractions**2)), 1.0)


def baseline(wavelength_nm):
    """Solvent/plate background: rising into the UV."""
    return 0.05 + 0.3 * (np.asarray(wavelength_nm, dtype=float) / 200.0) ** -4


def band_height(row, solids=True) -> float:
    """Peak absorbance of one plate-map well; 0 for a solvent-only (blank) plate."""
    height = BAND_HEIGHTS.get(row["solute"], BAND_HEIGHT)
    return height * dissolved_fraction(row[FRACTION_COLUMNS], row["solute"]) if solids else 0.0


def attack(fractions, delay_min, wavelength_nm):
    """Plate attack: solvent-weighted absorbance growing with contact time, rising into the UV like the baseline."""
    rate = sum(f * ATTACK_PER_MIN.get(s, 0.0) for f, s in zip(fractions, ALL_SOLVENTS))
    return rate * delay_min * (np.asarray(wavelength_nm, dtype=float) / 300.0) ** -4


def _band(solute, height):
    peak, width = PEAK_NM[solute], WIDTH_NM[solute]
    return height * np.exp(-0.5 * ((WAVELENGTHS - peak) / width) ** 2)


def spectrum(row, rng, solids=True, delay_min=0.0) -> np.ndarray:
    """Absorbance at every wavelength for one well."""
    fractions = row[FRACTION_COLUMNS].to_numpy(dtype=float)
    return np.minimum(baseline(WAVELENGTHS) + _band(row["solute"], band_height(row, solids)) + attack(fractions, delay_min, WAVELENGTHS)
                      + rng.normal(0, NOISE, WAVELENGTHS.size), READER_MAX)


def _long(spectra_by_well) -> pd.DataFrame:
    frames = [pd.DataFrame({"well": well, "wavelength_nm": WAVELENGTHS, "absorbance": a}) for well, a in spectra_by_well]
    return pd.concat(frames, ignore_index=True).round({"absorbance": 4})


def spectra_export(plate_map, rng, solids=True, delay_min=0.0) -> pd.DataFrame:
    """Full-spectrum export as a long table (well, wavelength_nm, absorbance), readable by bo_bridge merge."""
    return _long((well, spectrum(row, rng, solids, delay_min)) for well, row in plate_map.iterrows())


def fixed_wavelength_export(spectra_long, wavelengths_nm) -> pd.DataFrame:
    """Keep only the given wavelengths of a full-spectrum export, as a reader set to fixed wavelengths would give."""
    return spectra_long[spectra_long["wavelength_nm"].isin(list(wavelengths_nm))].reset_index(drop=True)


def qc_spectrum(row, rng, delay_min=0.0) -> np.ndarray:
    """One QC-plate well: blank = solvent background only; calibration = the loaded mass, capped by solubility in that pure solvent."""
    fractions = np.array([row.get(f"frac_{s}", 0.0) for s in ALL_SOLVENTS], dtype=float)
    band = 0.0
    if row["role"] == "calibration":
        solubility = dissolved_fraction(fractions, row["solute"])  # as a fraction of the nominal mass
        band = _band(row["solute"], BAND_HEIGHTS.get(row["solute"], BAND_HEIGHT) * min(float(row["loading"]), solubility))
    return np.minimum(baseline(WAVELENGTHS) + band + attack(fractions, delay_min, WAVELENGTHS) + rng.normal(0, NOISE, WAVELENGTHS.size), READER_MAX)


def qc_export(qc_map, rng, delay_min=0.0) -> pd.DataFrame:
    """Full-spectrum export of a QC plate (analysis.qc_layout.qc_plate_map)."""
    return _long((well, qc_spectrum(row, rng, delay_min)) for well, row in qc_map.iterrows())


def plate_log(plate_labels, rng, mean_min=8.0, spread_min=4.0) -> pd.DataFrame:
    """Fake lab log: minutes between the end of shaking and the read, per plate."""
    delays = np.clip(rng.normal(mean_min, spread_min, len(plate_labels)), 1.0, None).round(1)
    return pd.DataFrame({"plate": plate_labels, "read_delay_min": delays})


def endpoint_export(plate_map, rng, solids=True) -> pd.DataFrame:
    """Single-value export (well, absorbance): each well read at its own solute's peak wavelength."""
    values = [baseline(PEAK_NM[row["solute"]]) + band_height(row, solids) + rng.normal(0, NOISE)
              for _, row in plate_map.iterrows()]
    return pd.DataFrame({"well": plate_map.index, "absorbance": np.round(values, 4)})
