"""Plate-reader .xlsx workbooks in uvvis/ -> the .csv files the analysis reads (well, wavelength_nm, absorbance).

    python -m production.convert_reader_xlsx CSV_DIR/uvvis --round N

run_bo.sh calls this for the round it is about to analyse. Every uvvis/reader_roundN_*.xlsx gets a .csv of the same name
next to it, unless a .csv at least as new is already there (a hand-made .csv always wins).

The workbook is the Tecan i-control export (Infinite 200 PRO): instrument and scan-settings rows, then a row 'Wavel.' with
the wavelengths across, one row per well (A1, A2, ...) and an 'End Time:' row. Each workbook must hold exactly one scan
sheet (empty sheets are ignored); one with several scans stops with their sheet names, so a plate is never taken from the
wrong sheet. The block is found in either orientation (wells as rows, or wells across with wavelengths down), so the rows
around it are ignored and any wavelength range and step is read. Numbers stored as text with decimal commas are read
too. An over-range reading ("OVER", ">4")
becomes OVER_ABS, so the analysis treats that wavelength as opaque and flags the well saturated; any other non-numeric
reading stops the conversion with the wells it affects.
"""
import argparse
import re
import sys
from pathlib import Path

import pandas as pd

from analysis.spectra import SpectraError, normalize_well

OVER_ABS = 4.0  # stands in for an over-range reading: above the blank limit (1.0); analysis flags >= this as saturated
_OVER = re.compile(r"\s*(over\w*|>.*)\s*", re.IGNORECASE)


def _number(x):
    """A cell as float: numbers, or text like '0,4982' / '0.4982'; None for anything else (blank, labels)."""
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return None if pd.isna(x) else float(x)
    try:
        return float(str(x).strip().replace(",", "."))
    except ValueError:
        return None


def _reading(x):
    """An absorbance cell as float: a number, OVER_ABS for an over-range reading, None for anything else."""
    return OVER_ABS if isinstance(x, str) and _OVER.fullmatch(x) else _number(x)


def _well(x):
    try:
        return normalize_well(x) if isinstance(x, str) else None
    except SpectraError:
        return None


def _block(grid):
    """Long table (well, wavelength_nm, absorbance) from one sheet's cells, or None if the sheet has no spectra block."""
    for r in range(len(grid)):
        row = grid.iloc[r]
        # wells across: this row holds well names, the rows below start with a wavelength
        across = {c: w for c, x in row.items() if (w := _well(x))}
        if len(across) >= 2:
            data = []
            for rr in range(r + 1, len(grid)):
                nm = _number(grid.iat[rr, min(across) - 1]) if min(across) > 0 else None
                if nm is None:
                    break
                data += [(w, nm, grid.iat[rr, c]) for c, w in across.items()]
            if data:
                return data
        # wells as rows: this row's first cell is a well, the nearest non-empty row above holds the wavelengths
        if (first := _well(row.iloc[0])) is not None:
            header = next((grid.iloc[h] for h in range(r - 1, -1, -1) if grid.iloc[h].notna().any()), None)
            nms = {c: nm for c, x in header.items() if c > 0 and (nm := _number(x)) is not None} if header is not None else {}
            if nms:
                data = []
                for rr in range(r, len(grid)):
                    w = _well(grid.iat[rr, 0])
                    if w is None:
                        break
                    data += [(w, nm, grid.iat[rr, c]) for c, nm in nms.items()]
                return data
    return None


def _scans(path) -> dict:
    """{sheet name: spectra block} for every sheet of the workbook that holds one."""
    scans = {}
    for name, grid in pd.read_excel(path, sheet_name=None, header=None).items():
        grid.columns = range(grid.shape[1])
        if data := _block(grid):
            scans[name] = data
    return scans


def read_xlsx(path) -> pd.DataFrame:
    """The one scan in a plate-reader workbook as a long table; SpectraError if there is none, several, or a bad reading."""
    scans = _scans(path)
    if not scans:
        raise SpectraError(f"{path}: no spectra block found (a 'Wavel.' header with one row per well, or wells across)")
    if len(scans) > 1:
        raise SpectraError(f"{path}: {len(scans)} scans (sheets {list(scans)}); save one plate per workbook")
    (name, data), = scans.items()
    df = pd.DataFrame(data, columns=["well", "wavelength_nm", "absorbance"])
    values = df["absorbance"].map(_reading)
    bad = sorted(set(df.loc[values.isna(), "well"]))
    if bad:
        raise SpectraError(f"{path} (sheet {name!r}): non-numeric readings in wells {bad}")
    return df.assign(absorbance=values)


def convert_round(uvvis, round_) -> list:
    """Convert uvvis/reader_round<round_>_*.xlsx to .csv where needed; returns the .csv paths written."""
    written = []
    for xlsx in sorted(Path(uvvis).glob(f"reader_round{round_}_*.xlsx")):
        out = xlsx.with_suffix(".csv")
        if out.exists() and out.stat().st_mtime >= xlsx.stat().st_mtime:
            continue
        read_xlsx(xlsx).to_csv(out, index=False)
        written.append(out)
    return written


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("uvvis", help="the uvvis/ folder")
    ap.add_argument("--round", type=int, required=True, help="round whose reader_roundN_*.xlsx to convert")
    args = ap.parse_args()
    try:
        for out in convert_round(args.uvvis, args.round):
            print(f"  converted {out.with_suffix('.xlsx').name} -> {out.name}")
    except SpectraError as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
