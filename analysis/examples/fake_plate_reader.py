"""Fake plate reader: synthetic absorbance data for a plate map written by `OT protocols/bo_bridge.py layout`.

Solvent and solute names come from production/config.toml so the fake data chains with bo_bridge and SDL_BO; the
band positions and dissolving powers are invented. Each solute has one Gaussian absorption band whose height scales
with a made-up "dissolved fraction" that rewards balanced mixtures, so a mixture can beat every pure solvent as the
project hypothesis predicts. Debugging only: none of the numbers are real.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from production.config import ALL_SOLVENTS, FIRST_ROUND, GREEN_SOLVENTS, PLATE_ATTACKERS, SOLUTES, blank_column  # noqa: E402

FRACTION_COLUMNS = [f"frac_{s}" for s in ALL_SOLVENTS]
WAVELENGTHS = np.arange(200, 705, 5)  # nm: the plate reader's 200-700 nm scan in 5 nm steps
# Invented band centre / width per solute (production order); only the Phthalimide value is anywhere near reality.
PEAK_NM = dict(zip(SOLUTES, [275, 350, 295, 410]))
WIDTH_NM = dict(zip(SOLUTES, [18, 25, 22, 35]))
BAND_HEIGHT = 1.2  # peak absorbance of a fully dissolved solute
BAND_HEIGHTS = {}  # per-solute override of BAND_HEIGHT, e.g. {SOLUTES[0]: 2.6} to saturate, {SOLUTES[3]: 0.06} to sit near the noise
ATTACK_PER_MIN = {}  # solvent -> absorbance gained per minute of contact at 300 nm (polystyrene attack); default none
CUTOFF_NM = {}  # solvent -> UV cut-off: the solvent itself absorbs strongly below this wavelength; default none
CUTOFF_ABS = 3.0  # absorbance a pure solvent reaches well below its cut-off (the reader clips at READER_MAX)
NOISE = 0.004
READER_MAX = 3.5  # the reader cannot report more than this absorbance
SYNERGY = 0.4  # bonus for balanced mixtures: 0 for a pure solvent, up to SYNERGY * 2/3 for an equal ternary

# Made-up dissolving power (0-1) of each solvent (production order, reference first) for each solute; DMF dissolves everything.
_POWERS = [[1, .7, .4, .6, .5, .3, .4], [1, .3, .6, .5, .2, .7, .4], [1, .5, .3, .4, .7, .6, .3], [1, .4, .5, .6, .3, .5, .7]]
POWER = pd.DataFrame({solute: col[: len(ALL_SOLVENTS)] for solute, col in zip(SOLUTES, _POWERS)}, index=ALL_SOLVENTS)


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


def solvent_absorbance(fractions, wavelength_nm):
    """Solvent cut-offs: each solvent's own absorbance rises sigmoidally below CUTOFF_NM[solvent], weighted by its fraction."""
    wl = np.asarray(wavelength_nm, dtype=float)
    return sum(f * CUTOFF_ABS / (1 + np.exp((wl - CUTOFF_NM[s]) / 8.0)) for f, s in zip(fractions, ALL_SOLVENTS) if s in CUTOFF_NM)


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
    return np.minimum(baseline(WAVELENGTHS) + solvent_absorbance(fractions, WAVELENGTHS) + _band(row["solute"], band_height(row, solids)) + attack(fractions, delay_min, WAVELENGTHS)
                      + rng.normal(0, NOISE, WAVELENGTHS.size), READER_MAX)


def _long(spectra_by_well) -> pd.DataFrame:
    frames = [pd.DataFrame({"well": well, "wavelength_nm": WAVELENGTHS, "absorbance": a}) for well, a in spectra_by_well]
    return pd.concat(frames, ignore_index=True).round({"absorbance": 4})


def spectra_export(plate_map, rng, solids=True, delay_min=0.0) -> pd.DataFrame:
    """Full-spectrum export as a long table (well, wavelength_nm, absorbance), readable by bo_bridge merge."""
    return _long((well, spectrum(row, rng, solids, delay_min)) for well, row in plate_map.iterrows())


def solvent_blank_export(rng, delay_min=0.0, round_=None) -> pd.DataFrame:
    """The solvent blank plate as read after round_ (default: the first round), as a long table like `spectra_export`:
    one pure-solvent well per solvent (A DMF, B acetone, ... in config order) in every column filled so far (1..round + 1)."""
    columns = range(1, blank_column(FIRST_ROUND if round_ is None else round_) + 1)
    index = [f"{'ABCDEFGH'[i]}{c}" for c in columns for i in range(len(ALL_SOLVENTS))]
    wells = pd.DataFrame(np.tile(np.eye(len(ALL_SOLVENTS)), (len(columns), 1)), columns=FRACTION_COLUMNS, index=index)
    return spectra_export(wells.assign(solute=SOLUTES[0]), rng, solids=False, delay_min=delay_min)


def tecan_rows(spectra_long) -> list:
    """Cells of one Tecan i-control absorbance-scan sheet (Infinite 200 PRO), as the lab's plate reader saves it: settings
    rows, a 'Wavel.' header with the wavelengths across, one row per well and an 'End Time:' row. Readings at
    READER_MAX are written as the text 'OVER', as the reader does."""
    wide = spectra_long.pivot(index="well", columns="wavelength_nm", values="absorbance").reindex(spectra_long["well"].unique())
    nm = [int(w) for w in wide.columns]
    setting = lambda label, value, unit=None: [label, None, None, None, value] + ([unit] if unit else [])
    meta = {1: setting("Application: Tecan i-control", "Tecan i-control , 2.0.10.0"), 2: setting("Device: infinite 200Pro", "Serial number: 0"),
            5: ["Date:", "19.10.2026"], 6: ["Time:", "18:47:23"], 11: setting("Plate", "Sarstedt 96 Flat Bottom Transparent"),
            16: setting("Mode", "Absorbance"), 17: setting("Wavelength Start", nm[0], "nm"), 18: setting("Wavelength End", nm[-1], "nm"),
            19: setting("Wavelength Step Size", nm[1] - nm[0] if len(nm) > 1 else 0, "nm"), 20: setting("Scan Number", len(nm)),
            25: setting("Part of Plate", f"{wide.index[0]}-{wide.index[-1]}"), 26: ["Start Time:", "19.10.2026 18:47:23"],
            28: [None, "Temperature: 26 °C"]}
    rows = [meta.get(i, []) for i in range(1, 29)] + [["Wavel."] + nm]
    rows += [[w] + ["OVER" if v >= READER_MAX else float(v) for v in vals] for w, vals in wide.iterrows()]
    return rows + [[]] * 4 + [["End Time:", "19.10.2026 18:49:40"]]


def write_plate_reader_xlsx(spectra_long, path) -> None:
    """Write a spectra table as the plate reader's workbook: one scan sheet (tecan_rows) plus the empty sheet Excel adds."""
    with pd.ExcelWriter(path) as workbook:
        pd.DataFrame(tecan_rows(spectra_long)).to_excel(workbook, sheet_name="Absorbance scan", header=False, index=False)
        pd.DataFrame().to_excel(workbook, sheet_name="Sheet1")


def write_plate_reader_csv(spectra_long, path) -> None:
    """Write a spectra table as a ';'-separated CSV with decimal commas, one row per well under a 'Wavel.' header (a
    hand-made .csv run_bo.sh also accepts; the reader itself saves .xlsx, see write_plate_reader_xlsx)."""
    wide = spectra_long.pivot(index="well", columns="wavelength_nm", values="absorbance").reindex(spectra_long["well"].unique())
    wide.columns = wide.columns.astype(int)
    wide.to_csv(path, sep=";", decimal=",", index_label="Wavel.", lineterminator="\r\n")


def fixed_wavelength_export(spectra_long, wavelengths_nm) -> pd.DataFrame:
    """Keep only the given wavelengths of a full-spectrum export, as a reader set to fixed wavelengths would give."""
    return spectra_long[spectra_long["wavelength_nm"].isin(list(wavelengths_nm))].reset_index(drop=True)


def plate_log(plate_labels, rng, mean_min=8.0, spread_min=4.0) -> pd.DataFrame:
    """Fake lab log: minutes between the end of shaking and the read, per plate."""
    delays = np.clip(rng.normal(mean_min, spread_min, len(plate_labels)), 1.0, None).round(1)
    return pd.DataFrame({"plate": plate_labels, "read_delay_min": delays})


def endpoint_export(plate_map, rng, solids=True) -> pd.DataFrame:
    """Single-value export (well, absorbance): each well read at its own solute's peak wavelength."""
    values = [baseline(PEAK_NM[row["solute"]]) + band_height(row, solids) + rng.normal(0, NOISE)
              for _, row in plate_map.iterrows()]
    return pd.DataFrame({"well": plate_map.index, "absorbance": np.round(values, 4)})
