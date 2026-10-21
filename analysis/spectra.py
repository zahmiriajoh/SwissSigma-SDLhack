"""Plate-reader spectra -> one absorbance per well, in the single-value export `bo_bridge.py merge` reads.

Input: one full-spectrum export per plate: the plate reader's own layout (one row per well, wavelengths across the header,
`;` separators and decimal commas), a long table (well, wavelength_nm, absorbance) or a wavelength-by-well matrix. The plate map from `bo_bridge.py layout` says which
solute sits in each well. Each solute is read at its own wavelength: the peak of its blank-corrected
DMF-control spectrum, unless overridden. Output per plate: (well, absorbance) at that wavelength.

Blank handling: the solvent-only readings are used here only to find the peaks. The endpoint files keep the
raw absorbance (plates and blank alike), so `bo_bridge.py merge --blank` does the one and only subtraction.
The blank is optional: a full solvent-only copy of the sample plate, or (the plan) one pure-solvent well per solvent
from which `predicted_blank` builds every well's background. Without either nothing is subtracted.
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

from production.config import ALL_SOLVENTS, FIRST_ROUND, blank_column

ROWS = "ABCDEFGH"
N_COLS = 12
WELLS = [f"{r}{c}" for r in ROWS for c in range(1, N_COLS + 1)]  # row order, as in bo_bridge


def solvent_wells(round_=FIRST_ROUND) -> dict:
    """Pure-solvent blank wells of round_: solvent i of the config in row i of that round's column (A1 DMF ... in round 0,
    A2 DMF ... in round 1), as the OT-2 protocol fills the solvent blank plate."""
    column = blank_column(round_)
    return {s: f"{ROWS[i]}{column}" for i, s in enumerate(ALL_SOLVENTS)}


SOLVENT_WELLS = solvent_wells()  # the first round's: A1 DMF, B1 acetone, ... in config order
CONTROL_ROLE = "control"  # plate-map role of the DMF reference wells
DEFAULT_NM_RANGE = (200.0, 700.0)  # the whole scanned spectrum
MAX_SCAN_STEP_NM = 5  # the scan step (nm): a picked wavelength within one step of the band maximum counts as at it
BLANK_MAX_DEFAULT = 1.0  # a wavelength is usable only where every solvent blank stays below this absorbance (PLAN decision 15)
NOISE_NM = (600.0, 700.0)  # no solute absorbs here: the spread of the corrected control spectrum estimates the reader noise
MIN_SIGNAL_SIGMAS = 3.0    # a solute counts as measurable when its control signal exceeds this many noise sigmas
ABS_MAX_DEFAULT = 2.5    # reader linear range placeholder: raw absorbance above it is flagged "saturated" (PLAN decision 5)


class SpectraError(ValueError):
    """The reader export or plate map cannot be used as-is."""


def normalize_well(name) -> str:
    """'a01' -> 'A1'; SpectraError for anything that is not a 96-well name."""
    m = re.fullmatch(r"\s*([A-Ha-h])\s*0*([1-9]|1[0-2])\s*", str(name))
    if not m:
        raise SpectraError(f"'{name}' is not a well name (A1-H12)")
    return f"{m.group(1).upper()}{m.group(2)}"


def _find_column(df, test):
    return next((c for c in df.columns if test(str(c).strip().lower())), None)


def _read_table(path) -> pd.DataFrame:
    """CSV with ',' separators and '.' decimals, or ';' separators and ',' decimals (European locale export)."""
    semicolon = ";" in Path(path).read_text().splitlines()[0]
    return pd.read_csv(path, sep=";" if semicolon else ",", decimal="," if semicolon else ".")


def _is_well(name) -> bool:
    try:
        normalize_well(name)
        return True
    except SpectraError:
        return False


def read_spectra(path) -> pd.DataFrame:
    """Wide table: index wavelength_nm (float, sorted), one column per well.

    Accepts a long table (well, wavelength, absorbance), a wavelength-by-well matrix, or its transpose (one row per
    well, wavelengths across the header, as the plate reader exports it).
    """
    df = _read_table(path)
    wl_col = _find_column(df, lambda c: "wavel" in c or c in ("nm", "lambda"))
    well_col = _find_column(df, lambda c: c == "well")
    if well_col is None and df.iloc[:, 0].map(_is_well).all():  # wells down the rows: transpose
        wide = df.set_index(df.columns[0]).T
    elif wl_col is None:
        raise SpectraError(f"{path}: no wavelength column (expected 'wavelength_nm')")
    elif well_col is not None:  # long table
        value_col = next((c for c in df.columns if c not in (wl_col, well_col)
                          and pd.api.types.is_numeric_dtype(df[c])), None)
        if value_col is None:
            raise SpectraError(f"{path}: no numeric absorbance column")
        wide = df.pivot(index=wl_col, columns=well_col, values=value_col)
    else:  # wavelength-by-well matrix
        wide = df.set_index(wl_col)
    wide.columns = [normalize_well(c) for c in wide.columns]
    wide.index = wide.index.astype(float)
    wide.index.name = "wavelength_nm"
    return wide.sort_index()


def read_plate_map(path) -> pd.DataFrame:
    """A bo_bridge plate map indexed by well; needs columns well, solute, role."""
    pm = pd.read_csv(path)
    missing = [c for c in ("well", "solute", "role") if c not in pm.columns]
    if missing:
        raise SpectraError(f"{path}: plate map lacks columns {missing}")
    pm["well"] = pm["well"].map(normalize_well)
    return pm.set_index("well")


def blank_correct(spectra, blank) -> pd.DataFrame:
    """Subtract the solvent-only plate well by well; wells and wavelengths must match."""
    missing = spectra.columns.difference(blank.columns)
    if len(missing):
        raise SpectraError(f"blank plate lacks wells {list(missing)}")
    blank = blank.reindex(spectra.index)
    if blank[spectra.columns].isna().any().any():
        raise SpectraError("blank plate was read at different wavelengths from the sample plates")
    return spectra - blank[spectra.columns]


def predicted_blank(solvent_spectra, plate_map) -> pd.DataFrame:
    """Blank plate predicted from one pure-solvent well per solvent (solvent_wells of the plate map's round): each well's
    blank is the volume-fraction-weighted sum of the pure-solvent spectra (equal path length, ideal mixing). Wavelength x well."""
    wells = solvent_wells(plate_map["round"].iloc[0])
    check_wells(solvent_spectra, pd.DataFrame(index=list(wells.values())), "solvent blank")
    fraction_cols = [f"frac_{s}" for s in wells]
    missing = [c for c in fraction_cols if c not in plate_map.columns]
    if missing:
        raise SpectraError(f"plate map lacks columns {missing}")
    pure = solvent_spectra[list(wells.values())].set_axis(list(wells), axis=1)
    return pure @ plate_map[fraction_cols].set_axis(list(wells), axis=1).T


def check_wells(spectra, plate_map, name="reader export") -> None:
    """Every plate-map well has a spectrum."""
    missing = plate_map.index.difference(spectra.columns)
    if len(missing):
        raise SpectraError(f"{name}: no spectrum for wells {list(missing)}")


def usable_mask(blank_wide, blank_max=BLANK_MAX_DEFAULT) -> pd.Series:
    """True at wavelengths where the worst blank column (pure solvent or blank well) stays below blank_max.

    Reading only there keeps every well, whatever its solvent mixture, out of the region where the solvent itself
    saturates the detector; by additivity a mixture's blank never exceeds its worst pure solvent's.
    """
    return blank_wide.max(axis=1) < blank_max


def nearest_nm(index, nm) -> float:
    """The scanned wavelength closest to nm (a fixed wavelength off the 5 nm grid would read nothing)."""
    return float(index[np.abs(index.to_numpy(dtype=float) - float(nm)).argmin()])


def pick_wavelengths(spectra_list, plate_map, nm_range=DEFAULT_NM_RANGE, overrides=None, usable=None):
    """Wavelength per solute: peak of the mean DMF-control spectrum over all plates, within nm_range and,
    if given, within the `usable` mask (wavelengths where every solvent is transparent enough).

    Returns (wavelengths Series, report DataFrame). The report says, per solute, where the unrestricted band maximum
    lies, whether the picked wavelength is that maximum or a shoulder, the usable window, and how much of the control
    signal is left at the picked wavelength. `overrides` ({solute: nm}) win over the picked values, snapped to the scan.
    """
    controls = plate_map[plate_map["role"] == CONTROL_ROLE]
    lo, hi = nm_range
    rows = []
    for solute, block in controls.groupby("solute"):
        spec = pd.concat([s.loc[lo:hi, block.index] for s in spectra_list], axis=1).mean(axis=1)
        band_max = float(spec.idxmax())
        allowed = spec if usable is None else spec[usable.reindex(spec.index).fillna(False).to_numpy()]
        if allowed.empty:
            raise SpectraError(f"{solute}: no usable wavelength in {lo:.0f}-{hi:.0f} nm (every point has a solvent blank above the limit)")
        full = pd.concat([s[block.index] for s in spectra_list], axis=1).mean(axis=1)
        nm = nearest_nm(full.index, overrides[solute]) if overrides and solute in overrides else float(allowed.idxmax())
        tail = full.loc[NOISE_NM[0]:NOISE_NM[1]]
        noise = float(tail.std()) if len(tail) > 3 else np.nan
        signal = float(spec.get(nm, np.nan))
        rows.append({"solute": solute, "wavelength_nm": nm, "band_max_nm": band_max, "at_band_max": abs(nm - band_max) <= MAX_SCAN_STEP_NM,
                     "window_min_nm": float(allowed.index.min()), "window_max_nm": float(allowed.index.max()),
                     "control_signal": signal, "signal_fraction": signal / spec.loc[band_max] if spec.loc[band_max] > 0 else np.nan,
                     "noise": noise, "measurable": bool(signal > MIN_SIGNAL_SIGMAS * noise) if noise == noise else True})
    for solute, nm in (overrides or {}).items():
        if solute not in {r["solute"] for r in rows}:
            rows.append({"solute": solute, "wavelength_nm": float(nm), "band_max_nm": np.nan, "at_band_max": True,
                         "window_min_nm": np.nan, "window_max_nm": np.nan, "control_signal": np.nan, "signal_fraction": np.nan,
                         "noise": np.nan, "measurable": True})
    columns = ["solute", "wavelength_nm", "band_max_nm", "at_band_max", "window_min_nm", "window_max_nm", "control_signal",
               "signal_fraction", "noise", "measurable"]
    report = pd.DataFrame(rows, columns=columns).set_index("solute")
    no_wavelength = set(plate_map["solute"]) - set(report.index)
    if no_wavelength:
        raise SpectraError(f"solutes {sorted(no_wavelength)} have no DMF control well; pass --wavelength for them")
    return report["wavelength_nm"], report


def reduce_plate(spectra, plate_map, wavelengths, bandwidth_nm=0.0, blank=None, abs_max=ABS_MAX_DEFAULT, blank_max=BLANK_MAX_DEFAULT) -> pd.DataFrame:
    """(well, absorbance, blank_abs, flag): each well read at its solute's wavelength, averaged over +/- bandwidth_nm.

    `flag` is "saturated" (raw above abs_max), "opaque" (that well's blank above blank_max) or both; bo_bridge merge
    reads only the first numeric column, so the extra columns are harmless there.
    """
    check_wells(spectra, plate_map)
    rows = []
    for well, solute in plate_map["solute"].items():
        wl = wavelengths[solute]
        a = spectra.loc[wl - bandwidth_nm: wl + bandwidth_nm, well].mean()
        b = blank.loc[wl - bandwidth_nm: wl + bandwidth_nm, well].mean() if blank is not None and well in blank.columns else np.nan
        flags = (["saturated"] if a > abs_max else []) + (["opaque"] if b > blank_max else [])
        rows.append((well, a, b, "+".join(flags)))
    return pd.DataFrame(rows, columns=["well", "absorbance", "blank_abs", "flag"]).round({"absorbance": 4, "blank_abs": 4})


def reduce_round(plate_map, plates, blank=None, overrides=None, nm_range=DEFAULT_NM_RANGE, bandwidth_nm=0.0,
                 blank_max=BLANK_MAX_DEFAULT, abs_max=ABS_MAX_DEFAULT):
    """Full step for one round.

    Returns (wavelengths, endpoints, corrected, report): wavelengths per solute; endpoint tables for each plate and
    (last, if given) the blank, in input order; the blank-corrected spectra used to pick the peaks; the wavelength report.
    The usable window comes from the blank plate; without one every wavelength in nm_range is usable.
    """
    for i, s in enumerate(plates, start=1):
        check_wells(s, plate_map, f"plate {i}")
    corrected = [blank_correct(s, blank) for s in plates] if blank is not None else list(plates)
    usable = usable_mask(blank, blank_max) if blank is not None else None
    wavelengths, report = pick_wavelengths(corrected, plate_map, nm_range, overrides, usable)
    to_reduce = plates + ([blank] if blank is not None else [])
    endpoints = [reduce_plate(s, plate_map, wavelengths, bandwidth_nm, blank, abs_max, blank_max) for s in to_reduce]
    return wavelengths, endpoints, corrected, report
