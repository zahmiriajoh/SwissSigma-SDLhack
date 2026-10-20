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
NOISE = 0.004
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
    return BAND_HEIGHT * dissolved_fraction(row[FRACTION_COLUMNS], row["solute"]) if solids else 0.0


def spectrum(row, rng, solids=True) -> np.ndarray:
    """Absorbance at every wavelength for one well."""
    peak, width = PEAK_NM[row["solute"]], WIDTH_NM[row["solute"]]
    band = band_height(row, solids) * np.exp(-0.5 * ((WAVELENGTHS - peak) / width) ** 2)
    return baseline(WAVELENGTHS) + band + rng.normal(0, NOISE, WAVELENGTHS.size)


def spectra_export(plate_map, rng, solids=True) -> pd.DataFrame:
    """Full-spectrum export as a long table (well, wavelength_nm, absorbance), readable by bo_bridge merge."""
    frames = [pd.DataFrame({"well": well, "wavelength_nm": WAVELENGTHS, "absorbance": spectrum(row, rng, solids)})
              for well, row in plate_map.iterrows()]
    return pd.concat(frames, ignore_index=True).round({"absorbance": 4})


def endpoint_export(plate_map, rng, solids=True) -> pd.DataFrame:
    """Single-value export (well, absorbance): each well read at its own solute's peak wavelength."""
    values = [baseline(PEAK_NM[row["solute"]]) + band_height(row, solids) + rng.normal(0, NOISE)
              for _, row in plate_map.iterrows()]
    return pd.DataFrame({"well": plate_map.index, "absorbance": np.round(values, 4)})
