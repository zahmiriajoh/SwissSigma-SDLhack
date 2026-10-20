"""Plate-reader spectra -> one absorbance per well, in the single-value export `bo_bridge.py merge` reads.

Input: one full-spectrum export per plate, as a long table (well, wavelength_nm, absorbance) or a wide
matrix (wavelength_nm rows, one column per well). The plate map from `bo_bridge.py layout` says which
solute sits in each well. Each solute is read at its own wavelength: the peak of its blank-corrected
DMF-control spectrum, unless overridden. Output per plate: (well, absorbance) at that wavelength.

Blank handling: the solvent-only readings are used here only to find the peaks. The endpoint files keep the
raw absorbance (plates and blank alike), so `bo_bridge.py merge --blank` does the one and only subtraction.
The blank can be a full solvent-only copy of the sample plate, or a QC plate (qc_layout.py) whose pure-solvent
blank wells are combined per sample well in its volume fractions (synthetic_blank).
"""
import re

import pandas as pd

ROWS = "ABCDEFGH"
N_COLS = 12
WELLS = [f"{r}{c}" for r in ROWS for c in range(1, N_COLS + 1)]  # row order, as in bo_bridge
CONTROL_ROLE = "control"  # plate-map role of the DMF reference wells
DEFAULT_NM_RANGE = (230.0, 800.0)  # ignore the far-UV edge where solvents and plastics absorb
SMOOTH_NM = 5  # rolling-mean width before picking the peak, so one noisy point cannot win


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


def read_spectra(path) -> pd.DataFrame:
    """Wide table: index wavelength_nm (float, sorted), one column per well."""
    df = pd.read_csv(path)
    wl_col = _find_column(df, lambda c: "wavelength" in c or c in ("nm", "lambda"))
    well_col = _find_column(df, lambda c: c == "well")
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


def synthetic_blank(qc_spectra, qc_map, plate_map) -> pd.DataFrame:
    """Blank spectrum per sample well = sum over solvents of (volume fraction x pure-solvent blank spectrum from the QC plate).

    Returns a wide table (wavelength x plate-map wells) usable wherever a blank plate is, so the sample layout needs
    no solvent-only copy. Requires one pure-solvent blank well per solvent used in the plate map.
    """
    blanks = qc_map[(qc_map["role"] == "blank") & (qc_map["solvent"].notna()) & (qc_map["solvent"] != "")]
    pure = {row["solvent"]: qc_spectra[well] for well, row in blanks.iterrows() if well in qc_spectra.columns}
    cols = [c for c in plate_map.columns if c.startswith("frac_")]
    missing = {c[len("frac_"):] for c in cols if (plate_map[c] > 0).any()} - set(pure)
    if missing:
        raise SpectraError(f"QC plate has no pure-solvent blank well for {sorted(missing)}")
    out = {well: sum(row[f"frac_{s}"] * pure[s] for s in pure if row.get(f"frac_{s}", 0) > 0)
           for well, row in plate_map.iterrows()}
    return pd.DataFrame(out, index=qc_spectra.index)


def pick_wavelengths(spectra_list, plate_map, nm_range=DEFAULT_NM_RANGE, overrides=None) -> pd.Series:
    """Wavelength per solute: peak of the mean (smoothed) DMF-control spectrum over all plates, within nm_range.

    `spectra_list` should be blank-corrected so the solvent baseline does not shift the peak.
    `overrides` ({solute: nm}) win over the picked values and are also accepted for solutes without controls.
    """
    controls = plate_map[plate_map["role"] == CONTROL_ROLE]
    lo, hi = nm_range
    picked = {}
    for solute, block in controls.groupby("solute"):
        spec = pd.concat([s.loc[lo:hi, block.index] for s in spectra_list], axis=1).mean(axis=1)
        window = SMOOTH_NM if _is_full_spectrum(spec.index) else 1  # a few fixed wavelengths: no smoothing
        picked[solute] = float(spec.rolling(window, center=True, min_periods=1).mean().idxmax())
    picked.update({s: float(nm) for s, nm in (overrides or {}).items()})
    no_wavelength = set(plate_map["solute"]) - set(picked)
    if no_wavelength:
        raise SpectraError(f"solutes {sorted(no_wavelength)} have no DMF control well; pass --wavelength for them")
    return pd.Series(picked, name="wavelength_nm").rename_axis("solute")


def reduce_plate(spectra, plate_map, wavelengths, bandwidth_nm=0.0) -> pd.DataFrame:
    """(well, absorbance): each well read at its solute's wavelength, averaged over +/- bandwidth_nm."""
    check_wells(spectra, plate_map)
    values = []
    for well, solute in plate_map["solute"].items():
        wl = wavelengths[solute]
        values.append(spectra.loc[wl - bandwidth_nm: wl + bandwidth_nm, well].mean())
    return pd.DataFrame({"well": plate_map.index, "absorbance": values}).round(4)


def reduce_round(plate_map, plates, blank=None, overrides=None, nm_range=DEFAULT_NM_RANGE, bandwidth_nm=0.0):
    """Full step for one round.

    Returns (wavelengths, endpoints, corrected): wavelengths per solute; endpoint tables for each plate and
    (last, if given) the blank, in input order; and the blank-corrected spectra used to pick the peaks.
    """
    for i, s in enumerate(plates, start=1):
        check_wells(s, plate_map, f"plate {i}")
    corrected = [blank_correct(s, blank) for s in plates] if blank is not None else list(plates)
    wavelengths = pick_wavelengths(corrected, plate_map, nm_range, overrides)
    to_reduce = plates + ([blank] if blank is not None else [])
    endpoints = [reduce_plate(s, plate_map, wavelengths, bandwidth_nm) for s in to_reduce]
    return wavelengths, endpoints, corrected
