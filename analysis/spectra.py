"""Plate-reader spectra -> one absorbance per well, in the single-value export `bo_bridge.py merge` reads.

Input: one full-spectrum export per plate, as a long table (well, wavelength_nm, absorbance), a wide
matrix (wavelength_nm rows, one column per well), or the lab reader's own export (one row per well, one column
per wavelength, e.g. "Wavel.;300;310;..." then "A1;0,498;..."). Comma- or semicolon-separated; with semicolons,
decimal commas are read too. The plate map from `bo_bridge.py layout` says which
solute sits in each well. Each solute is read at its own wavelength: the peak of its blank-corrected
DMF-control spectrum, unless overridden. Output per plate: (well, absorbance) at that wavelength.

Blank handling: the solvent-only readings are used here only to find the peaks. The endpoint files keep the
raw absorbance (plates and blank alike), so `bo_bridge.py merge --blank` does the one and only subtraction.
The blank is optional: a full solvent-only copy of the sample plate. Without one (the current plan) nothing is subtracted.
"""
import re

import numpy as np
import pandas as pd

ROWS = "ABCDEFGH"
N_COLS = 12
WELLS = [f"{r}{c}" for r in ROWS for c in range(1, N_COLS + 1)]  # row order, as in bo_bridge
CONTROL_ROLE = "control"  # plate-map role of the DMF reference wells
DEFAULT_NM_RANGE = (230.0, 800.0)  # ignore the far-UV edge where solvents and plastics absorb
SMOOTH_NM = 5  # rolling-mean width before picking the peak, so one noisy point cannot win
BLANK_MAX_DEFAULT = 1.0  # a wavelength is usable only where every solvent blank stays below this absorbance (PLAN decision 15)
NOISE_NM = (600.0, 800.0)  # no solute absorbs here: the spread of the corrected control spectrum estimates the reader noise
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
    """The export as a table: ',' separated, or ';' separated with decimal commas (European locale)."""
    with open(path, encoding="utf-8-sig") as f:
        header = f.readline()
    if header.count(";") > header.count(","):
        return pd.read_csv(path, sep=";", decimal=",", encoding="utf-8-sig")
    return pd.read_csv(path, encoding="utf-8-sig")


def _wells_as_rows(df):
    """The reader's own layout - first column well names, other column names wavelengths - as wavelength x well, else None."""
    try:
        wavelengths = [float(c) for c in df.columns[1:]]
        wells = [normalize_well(w) for w in df.iloc[:, 0]]
    except (ValueError, SpectraError):
        return None
    wide = df.iloc[:, 1:].T
    wide.index, wide.columns = wavelengths, wells
    return wide.apply(pd.to_numeric)


def read_spectra(path) -> pd.DataFrame:
    """Wide table: index wavelength_nm (float, sorted), one column per well."""
    df = _read_table(path)
    wl_col = _find_column(df, lambda c: "wavelength" in c or c in ("nm", "lambda"))
    well_col = _find_column(df, lambda c: c == "well")
    if wl_col is None and (wide := _wells_as_rows(df)) is not None:  # the lab reader's export
        wide.index.name = "wavelength_nm"
        return wide.sort_index()
    if wl_col is None:
        raise SpectraError(f"{path}: no wavelength column (expected 'wavelength_nm')")
    if well_col is not None:  # long table
        value_col = next((c for c in df.columns if c not in (wl_col, well_col)
                          and pd.api.types.is_numeric_dtype(df[c])), None)
        if value_col is None:
            raise SpectraError(f"{path}: no numeric absorbance column")
        wide = df.pivot(index=wl_col, columns=well_col, values=value_col)
    else:  # wide matrix
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


def check_wells(spectra, plate_map, name="reader export") -> None:
    """Every plate-map well has a spectrum."""
    missing = plate_map.index.difference(spectra.columns)
    if len(missing):
        raise SpectraError(f"{name}: no spectrum for wells {list(missing)}")


def _is_full_spectrum(index) -> bool:
    """True for a dense scan (many points, ~1 nm apart), False for a handful of fixed wavelengths."""
    return len(index) >= 20 and float(pd.Series(index).diff().median()) <= 2.0


def usable_mask(blank_wide, blank_max=BLANK_MAX_DEFAULT) -> pd.Series:
    """True at wavelengths where the worst blank column (pure solvent or blank well) stays below blank_max.

    Reading only there keeps every well, whatever its solvent mixture, out of the region where the solvent itself
    saturates the detector; by additivity a mixture's blank never exceeds its worst pure solvent's.
    """
    return blank_wide.max(axis=1) < blank_max


def _is_full_spectrum(index) -> bool:
    """True for a dense scan (many points, ~1 nm apart), False for a handful of fixed wavelengths."""
    return len(index) >= 20 and float(pd.Series(index).diff().median()) <= 2.0


def pick_wavelengths(spectra_list, plate_map, nm_range=DEFAULT_NM_RANGE, overrides=None, usable=None):
    """Wavelength per solute: peak of the mean (smoothed) DMF-control spectrum over all plates, within nm_range and,
    if given, within the `usable` mask (wavelengths where every solvent is transparent enough).

    Returns (wavelengths Series, report DataFrame). The report says, per solute, where the unrestricted band maximum
    lies, whether the picked wavelength is that maximum or a shoulder, the usable window, and how much of the control
    signal is left at the picked wavelength. `overrides` ({solute: nm}) win over the picked values.
    """
    controls = plate_map[plate_map["role"] == CONTROL_ROLE]
    lo, hi = nm_range
    rows = []
    for solute, block in controls.groupby("solute"):
        spec = pd.concat([s.loc[lo:hi, block.index] for s in spectra_list], axis=1).mean(axis=1)
        window = SMOOTH_NM if _is_full_spectrum(spec.index) else 1  # a few fixed wavelengths: no smoothing
        smooth = spec.rolling(window, center=True, min_periods=1).mean()
        band_max = float(smooth.idxmax())
        allowed = smooth if usable is None else smooth[usable.reindex(smooth.index).fillna(False).to_numpy()]
        if allowed.empty:
            raise SpectraError(f"{solute}: no usable wavelength in {lo:.0f}-{hi:.0f} nm (every point has a solvent blank above the limit)")
        nm = float(overrides[solute]) if overrides and solute in overrides else float(allowed.idxmax())
        full = pd.concat([s[block.index] for s in spectra_list], axis=1).mean(axis=1)
        tail = full.loc[NOISE_NM[0]:NOISE_NM[1]]
        noise = float(tail.std()) if len(tail) > 3 else np.nan
        signal = float(smooth.get(nm, np.nan))
        rows.append({"solute": solute, "wavelength_nm": nm, "band_max_nm": band_max, "at_band_max": abs(nm - band_max) <= SMOOTH_NM,
                     "window_min_nm": float(allowed.index.min()), "window_max_nm": float(allowed.index.max()),
                     "control_signal": signal, "signal_fraction": signal / smooth.loc[band_max] if smooth.loc[band_max] > 0 else np.nan,
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
